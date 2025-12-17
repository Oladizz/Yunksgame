from telegram import Update, error
from telegram.ext import CallbackContext
import structlog
import random
import os
import json
import asyncio
import time
from telegram.error import RetryAfter, TimedOut, NetworkError

from ..game_logic.game_state import Game, GamePhase
from ..game_logic.player import Player, Role
from ..game_logic.farm import Farm, FarmLocation
from ..game_logic import interface
from . import core
from .. import database as db

logger = structlog.get_logger(__name__)

# --- Game Constants ---
FARMER_WIN_XP = 75
RAT_WIN_XP = 100

# --- Helper Functions ---

def all_players_acted(game: Game) -> bool:
    """Check if all non-expelled players have taken their action for the round."""
    return all(p.action_taken for p in game.players.values() if not p.is_expelled)

def reset_player_actions(game: Game):
    """Reset the action flag for all players for the next turn."""
    for player in game.players.values():
        player.action_taken = False

async def strict_edit_message(context, chat_id, message_id, new_text, new_markup, parse_mode='HTML'):
    # 1. RETRIEVE CACHED STATE
    # We use a unique key for every message to avoid conflicts
    cache_key = f"msg_cache_{chat_id}_{message_id}"
    last_state = context.chat_data.get(cache_key, {'text': None, 'markup': None})

    current_markup_json = None
    if new_markup:
        current_markup_json = json.dumps(new_markup.to_dict()) # Convert InlineKeyboardMarkup to dict then JSON string

    # 2. STRICT COMPARISON
    # If the new text AND new buttons are identical to the last successful update...
    if new_text == last_state['text'] and current_markup_json == last_state['markup']:
        # ...STOP HERE. Do not call the API.
        logger.debug(
            "Skipping update: Content unchanged",
            chat_id=chat_id,
            message_id=message_id,
            last_text=last_state['text'],
            new_text=new_text,
            last_markup_json=last_state['markup'],
            current_markup_json=current_markup_json
        )
        return 
    else:
        logger.info(
            "Attempting update: Content changed",
            chat_id=chat_id,
            message_id=message_id,
            last_text=last_state['text'],
            new_text=new_text,
            last_markup_json=last_state['markup'],
            current_markup_json=current_markup_json
        )

    # 3. SEND REQUEST (Only if content is different)
    max_retries = 3
    for i in range(max_retries):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_text,
                reply_markup=new_markup,
                parse_mode=parse_mode
            )
            
            # 4. UPDATE CACHE (Only on success)
            context.chat_data[cache_key] = {
                'text': new_text,
                'markup': current_markup_json # Store JSON string
            }
            return # Success! Exit function.
            
        except RetryAfter as e:
            logger.warning(f"Hit rate limit. Sleeping for {e.retry_after + 1} seconds for chat_id={chat_id}, message_id={message_id}.")
            await asyncio.sleep(e.retry_after + 1)
            # Loop will retry after waking up
            
        except TimedOut:
            logger.warning(f"Network timeout. Retrying in 1 second for chat_id={chat_id}, message_id={message_id}.")
            await asyncio.sleep(1)
            
        except error.BadRequest as e:
            if "Message is not modified" in str(e):
                # This handles the edge case where your cache was out of sync
                # We silently update the cache to match reality
                context.chat_data[cache_key] = {'text': new_text, 'markup': current_markup_json} # Store JSON string
                return # Treat as success, since state is now consistent
            else:
                logger.critical(f"Unhandled BadRequest error editing message: {e} for chat_id={chat_id}, message_id={message_id}. New text: {new_text}", exc_info=True)
                raise # Re-raise legitimate errors
            
        except Exception as e:
            logger.critical(f"Critical error in strict_edit_message: {e} for chat_id={chat_id}, message_id={message_id}. New text: {new_text}", exc_info=True)
            break

# --- Main Handler ---

async def handle_game_callback(update: Update, context: CallbackContext) -> None:
    """The main handler for all 'Rat in the Farm' game callbacks."""
    query = update.callback_query
    try:
        await query.answer()
    except error.BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning("Query is too old, couldn't answer.", data=query.data)
            return # Stop processing this old query
        else:
            raise

    user = query.from_user
    chat_id = query.message.chat_id
    db_client = context.bot_data['db']
    
    game: Game = context.chat_data.get('rat_game')
    if not game:
        await strict_edit_message(context, chat_id, query.message.message_id, "This game lobby has expired. Please start a new one with /farm.", None)
        return

    logger.info("Game phase", phase=game.phase)

    # Parse action data
    try:
        parts = query.data.split('_')
        command = parts[0] # "ratgame"
        
        if len(parts) > 1 and parts[1] == 'action':
            action = 'action'
            payload = '_'.join(parts[2:])
        elif len(parts) > 1 and parts[1] == 'accuse':
            action = 'accuse'
            payload = parts[2]
        elif len(parts) > 1 and parts[1] == 'reveal_role': # Added for role reveal button
            action = 'reveal_role'
            payload = parts[2] # player_id
        else:
            action = '_'.join(parts[1:])
            payload = None
    except IndexError:
        logger.warning("Malformed callback data received", data=query.data)
        return

    player = game.get_player(user.id)

    # --- HANDLE ROLE REVEAL ---
    if action == "reveal_role":
        revealed_player_id = int(payload)
        logger.info("Processing role reveal request", user_id=user.id, revealed_id=revealed_player_id, game_rat_id=game.rat_id)
        
        if user.id != revealed_player_id:
            logger.info("Attempting to send 'only own role' alert (User ID mismatch)", user_id=user.id, revealed_id=revealed_player_id)
            await query.answer("You can only reveal your own role!", show_alert=True)
            return
        
        if revealed_player_id == game.rat_id:
            logger.info("Attempting to send 'Rat role' alert", user_id=user.id, role="Rat")
            await query.answer("🐀 You are the Rat!", show_alert=True)
        else:
            logger.info("Attempting to send 'Farmer role' alert", user_id=user.id, role="Farmer")
            await query.answer("🌾 You are a Farmer.", show_alert=True)
        logger.info("Role revealed for player", game_id=chat_id, user_id=user.id, role=player.role.name)
        return # Stop further processing as role is revealed

    # --- LOBBY PHASE ---
    if game.phase == GamePhase.LOBBY:
        await handle_lobby_phase(update, context, game, action, user)

    # --- SEARCH & MOVEMENT PHASES ---
    elif game.phase in [GamePhase.SEARCH, GamePhase.MOVEMENT]:
        logger.info(
            "Search/Movement action attempt",
            game_id=chat_id,
            user_id=user.id,
            action=action,
            player_exists=(player is not None),
            action_taken=(player.action_taken if player else None)
        )
        if action == "action" and player and not player.action_taken:
            location = FarmLocation[payload]
            player.action_taken = True
            
            if player.role == Role.RAT:
                game.farm.move_rat(location)
                logger.info("Rat moved", game_id=chat_id, location=location.name)
            else:
                game.farm.locations[location]["searched_by"].add(player.user_id)
                logger.info("Farmer searched", game_id=chat_id, user_id=user.id, location=location.name)
            
            if all_players_acted(game):
                game.phase = GamePhase.RESULTS
                game.search_results = game.farm.process_searches()
                if game.farm.is_destroyed():
                    game.phase = GamePhase.RAT_WINS

    # --- RESULTS PHASE ---
    elif game.phase == GamePhase.RESULTS:
        if action == "proceed_suspicion":
            game.phase = GamePhase.SUSPICION

    # --- SUSPICION PHASE ---
    elif game.phase == GamePhase.SUSPICION:
        if action == "start_accusation":
            game.phase = GamePhase.ACCUSATION
        elif action == "next_round":
            game.round_number += 1
            game.farm.reset_round()
            reset_player_actions(game)
            game.phase = GamePhase.SEARCH

    # --- ACCUSATION PHASE ---
    elif game.phase == GamePhase.ACCUSATION:
        if action == "accuse":
            accused_id = int(payload)
            accused_player = game.get_player(accused_id)
            if accused_player:
                accused_player.is_expelled = True
                logger.info("Player expelled", game_id=chat_id, accused_id=accused_id)
                
                if accused_id == game.rat_id:
                    game.phase = GamePhase.FARMERS_WIN
                else:
                    game.farm.add_damage(25)
                    if game.farm.is_destroyed():
                        game.phase = GamePhase.RAT_WINS
                    else:
                        game.round_number += 1
                        game.farm.reset_round()
                        reset_player_actions(game)
                        game.phase = GamePhase.SEARCH
        elif action == "cancel_accusation":
            game.phase = GamePhase.SUSPICION
            
    # --- XP AWARDING FOR WINNERS ---
    if game.phase == GamePhase.FARMERS_WIN:
        for p in game.players.values():
            if p.role == Role.FARMER and not p.is_expelled:
                await db.add_xp(db_client, p.user_id, p.username, xp_to_add=FARMER_WIN_XP)
        logger.info("Farmers win, XP awarded", game_id=chat_id, xp=FARMER_WIN_XP)
        context.chat_data.pop('rat_game', None) # Clear game state
    
    elif game.phase == GamePhase.RAT_WINS:
        rat_player = game.get_player(game.rat_id)
        if rat_player:
            await db.add_xp(db_client, rat_player.user_id, rat_player.username, xp_to_add=RAT_WIN_XP)
        logger.info("Rat wins, XP awarded", game_id=chat_id, xp=RAT_WIN_XP)
        context.chat_data.pop('rat_game', None) # Clear game state


    # --- END GAME / NEW LOBBY ---
    if action == "new_lobby":
        await core.start_farm_game(update, context) # This will create a new game
        return

    # Re-render the game message with the new state
    logger.info("Attempting to render game message", game_id=game.game_message_id, current_phase=game.phase.name)
    text, keyboard = interface.get_game_render(game)

    # Implement UI Throttling
    THROTTLING_INTERVAL = 1.5 # seconds
    last_ui_update_timestamp = context.chat_data.get('last_ui_update_timestamp', 0)
    current_time = time.time() # Need to import time

    if current_time - last_ui_update_timestamp > THROTTLING_INTERVAL:
        # Implement "Smart Update" check here
        last_message_text = context.chat_data.get('last_msg_text')
        last_keyboard_json = context.chat_data.get('last_keyboard_json') # Store as JSON string for comparison

        current_keyboard_json = None
        if keyboard:
            current_keyboard_json = json.dumps(keyboard.to_dict()) # Convert InlineKeyboardMarkup to dict then JSON string

        if text != last_message_text or current_keyboard_json != last_keyboard_json:
            await strict_edit_message(context, chat_id, query.message.message_id, text, keyboard)
            # Update the stored state ONLY after success
            context.chat_data['last_msg_text'] = text
            context.chat_data['last_keyboard_json'] = current_keyboard_json
        
        # Update timestamp only if an update was attempted (even if content didn't change)
        context.chat_data['last_ui_update_timestamp'] = current_time
    else:
        # If throttled, log a message and do not update UI for this callback
        logger.info(
            "UI update throttled",
            chat_id=chat_id,
            game_id=game.game_message_id,
            time_since_last_update=current_time - last_ui_update_timestamp
        )

async def handle_lobby_phase(update: Update, context: CallbackContext, game: Game, action: str, user):
    """Handles all actions that can be taken during the LOBBY phase."""
    chat_id = update.effective_chat.id
    if action == "join":
        logger.info(
            "Join attempt",
            game_id=chat_id,
            user_id=user.id,
            players_in_game=list(game.players.keys()),
            is_user_in_game=(user.id in game.players)
        )
        if user.id not in game.players:
            game.add_player(Player(user.id, user.username or f"user{user.id}"))
            logger.info("Player joined lobby", game_id=chat_id, user_id=user.id)
    
    elif action == "leave":
        if user.id in game.players and user.id != game.owner_id:
            game.remove_player(user.id)
            logger.info("Player left lobby", game_id=chat_id, user_id=user.id)
        elif user.id == game.owner_id:
            await strict_edit_message(context, update.callback_query.message.chat_id, update.callback_query.message.message_id, "The game owner has left, and the lobby is closed.", None)
            context.chat_data.pop('rat_game', None)
            return

    elif action == "start_game":
        logger.info(
            "Game start attempt",
            game_id=chat_id,
            user_id=user.id,
            is_owner=(user.id == game.owner_id),
            player_count=len(game.players),
            min_players=game.min_players,
            phase_before=game.phase
        )
        if user.id != game.owner_id:
            await update.callback_query.answer("Only the game owner can start the game.", show_alert=True)
            return
        if len(game.players) < game.min_players:
            await update.callback_query.answer(f"You need at least {game.min_players} players to start.", show_alert=True)
            return
        
        logger.info("Game starting", game_id=chat_id, players=len(game.players))
        
        player_ids = list(game.players.keys())
        game.rat_id = random.choice(player_ids)
        game.get_player(game.rat_id).role = Role.RAT
        
        game.farm = Farm(locations=list(FarmLocation))
        game.phase = GamePhase.SEARCH
        game.round_number = 1
        reset_player_actions(game)
        logger.info("Game started, new phase", game_id=chat_id, new_phase=game.phase)