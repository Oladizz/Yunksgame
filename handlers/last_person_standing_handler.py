import html
import random
import asyncio
import time
from typing import Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import CallbackContext
import structlog

from Yunks_game import database as db
from Yunks_game.game_logic.last_person_standing import LastPersonStanding, GameStatus, EliminationReason
from Yunks_game.game_logic.player import Player # Reusing the Player class
from Yunks_game.handlers.game_handler import strict_edit_message # Reusing strict_edit_message

logger = structlog.get_logger(__name__)

# Game Constants
XP_AWARD_PER_WINNER = 3
INITIAL_WAIT_TIME = 5 # seconds before first elimination
ELIMINATION_INTERVAL = 10 # seconds between eliminations

async def start_lps_game(update: Update, context: CallbackContext) -> None:
    """Starts a new 'Last Person Standing' game lobby."""
    # This function can be called by a command (Update) or a button (CallbackQuery)
    if update.callback_query:
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
        reply_target = update.callback_query.message
    else:
        user = update.effective_user
        chat_id = update.effective_chat.id
        reply_target = update.message

    if 'last_person_standing_game' in context.chat_data:
        await reply_target.reply_text("A 'Last Person Standing' game is already in progress in this chat!")
        return

    logger.info("Starting new Last Person Standing game lobby", chat_id=chat_id, user_id=user.id)
    
    # Create a new game instance and add the creator
    game = LastPersonStanding(chat_id=chat_id, owner_id=user.id)
    game.add_player(Player(user.id, user.username or f"user{user.id}"))
    
    context.chat_data['last_person_standing_game'] = game

    # Render and send the lobby message
    text, keyboard = render_lps_game(game)
    message = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='HTML')    
    
    # Save the message ID to the game state so we can edit it later
    game.game_message_id = message.message_id

    # Initialize strict_edit_message cache for the newly sent message
    cache_key = f"msg_cache_{chat_id}_{message.message_id}"
    context.chat_data[cache_key] = {
        'text': text,
        'markup': keyboard.to_dict() if keyboard else None # Store dict for comparison
    }

async def handle_lps_callback(update: Update, context: CallbackContext) -> None:
    """The main handler for all 'Last Person Standing' game callbacks."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    db_client = context.bot_data['db']
    
    game: LastPersonStanding = context.chat_data.get('last_person_standing_game')
    if not game:
        await strict_edit_message(context, chat_id, query.message.message_id, "This game lobby has expired. Please start a new one.", None)
        return

    # Only owner can start the game
    if query.data == 'lps_start_game' and user.id != game.owner_id:
        await query.answer("Only the game owner can start the game.", show_alert=True)
        return

    # Process actions based on game status
    if game.status == GameStatus.LOBBY:
        await handle_lps_lobby_actions(update, context, game, user)
    elif game.status == GameStatus.RUNNING:
        # No direct player actions during RUNNING phase, eliminations are automatic
        pass # Potentially add spectator actions later
    
    # Always re-render the game message with the new state
    text, keyboard = render_lps_game(game)
    await strict_edit_message(context, chat_id, query.message.message_id, text, keyboard)

async def handle_lps_lobby_actions(update: Update, context: CallbackContext, game: LastPersonStanding, user: Player):
    """Handles actions specific to the LOBBY phase of Last Person Standing."""
    query = update.callback_query
    chat_id = query.message.chat_id

    if query.data == 'lps_join':
        if user.id not in game.players:
            game.add_player(Player(user.id, user.username or f"user{user.id}"))
            logger.info("Player joined LPS lobby", game_id=chat_id, user_id=user.id)
    
    elif query.data == 'lps_leave':
        if user.id in game.players and user.id != game.owner_id:
            game.remove_player(user.id)
            logger.info("Player left LPS lobby", game_id=chat_id, user_id=user.id)
        elif user.id == game.owner_id:
            await strict_edit_message(context, chat_id, query.message.message_id, "The game owner has left, and the lobby is closed.", None)
            context.chat_data.pop('last_person_standing_game', None)
            return # Game is over, no need to render

    elif query.data == 'lps_start_game':
        if len(game.players) < game.min_players_to_start:
            await query.answer(f"You need at least {game.min_players_to_start} player to start.", show_alert=True)
            return
        
        if game.start_game():
            logger.info("LPS game started", game_id=chat_id, players=len(game.players))
            
            # If 3 or fewer players start, they are the instant winners.
            if game.get_remaining_players_count() <= game.last_players_count:
                await context.bot.send_message(chat_id=chat_id, text="The game has started with 3 or fewer players. You are all winners!")
                
                winners = game.get_winners()
                db_client = context.bot_data['db']
                
                winner_usernames = []
                for winner in winners:
                    await db.add_xp(db_client, winner.user_id, winner.username, xp_to_add=XP_AWARD_PER_WINNER)
                    winner_usernames.append(f"@{html.escape(winner.username)}")
                
                final_message = (
                    f"🎉 <b>GAME OVER!</b> 🎉\n"
                    f"The winners are: {', '.join(winner_usernames)}!\n"
                    f"Each winner receives {XP_AWARD_PER_WINNER} XP!"
                )
                await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode='HTML')
                logger.info("LPS game finished instantly, XP awarded", chat_id=chat_id, winners=[w.user_id for w in winners])
                
                # Clear game state
                context.chat_data.pop('last_person_standing_game', None)

            else:
                # Schedule the first elimination for games with more than 3 players
                await context.bot.send_message(chat_id=chat_id, text="The game begins! Eliminating players soon...")
                context.job_queue.run_once(
                    initiate_elimination_loop, 
                    INITIAL_WAIT_TIME, 
                    data={'chat_id': chat_id, 'game_message_id': game.game_message_id},
                    name=f"lps_elimination_{chat_id}"
                )
            game.last_update_time = time.time() # Reset update time

async def initiate_elimination_loop(context: CallbackContext):
    """Starts a loop for player elimination."""
    chat_id = context.job.data['chat_id']
    game_message_id = context.job.data['game_message_id']
    game: LastPersonStanding = context.chat_data.get('last_person_standing_game')

    if not game or game.status != GameStatus.RUNNING:
        logger.info("Elimination loop stopped: game not running or not found.", chat_id=chat_id)
        context.job.schedule_removal() # Stop this job
        return

    elimination_result = game.eliminate_random_player()

    # Send elimination message if any player was eliminated
    if elimination_result:
        eliminated_player, reason = elimination_result
        elim_message = (
            f"❌ @{html.escape(eliminated_player.username)} {reason.value}\n"
            f"<b>{game.get_remaining_players_count()} players remaining!</b>"
        )
        await context.bot.send_message(chat_id=chat_id, text=elim_message, parse_mode='HTML')
    elif not elimination_result and game.get_remaining_players_count() > game.last_players_count:
        # If no one was eliminated but we still have too many players (shouldn't happen with random elimination unless list is empty)
        logger.warning("No player eliminated, but more than target players remaining. This indicates a logic error or empty player list.", players_remaining=game.get_remaining_players_count())
    
    # Always re-render the game message with the new state
    text, keyboard = render_lps_game(game)
    await strict_edit_message(context, chat_id, game_message_id, text, keyboard) 

    # Check if game should end now
    if game.get_remaining_players_count() <= game.last_players_count:
        # Game finished, award XP
        winners = game.get_winners() # This will now correctly set game.status to FINISHED
        db_client = context.bot_data['db']
        
        winner_usernames = []
        for winner in winners:
            await db.add_xp(db_client, winner.user_id, winner.username, xp_to_add=XP_AWARD_PER_WINNER)
            winner_usernames.append(f"@{html.escape(winner.username)}")
        
        final_message = (
            f"🎉 <b>GAME OVER!</b> 🎉\n"
            f"The winners are: {', '.join(winner_usernames)}!\n"
            f"Each winner receives {XP_AWARD_PER_WINNER} XP!"
        )
        await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode='HTML')
        logger.info("LPS game finished, XP awarded to winners", chat_id=chat_id, winners=[w.user_id for w in winners])
        
        # Clear game state and stop job
        context.chat_data.pop('last_person_standing_game', None)
        context.job.schedule_removal()
    else:
        # Game continues, schedule next elimination
        context.job_queue.run_once(
            initiate_elimination_loop, 
            ELIMINATION_INTERVAL, 
            data={'chat_id': chat_id, 'game_message_id': game.game_message_id},
            name=f"lps_elimination_{chat_id}"
        )

def render_lps_game(game: LastPersonStanding) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Renders the game message text and keyboard based on the current game state.
    """
    if game.status == GameStatus.LOBBY:
        player_list = "\n".join([f" - @{html.escape(p.username)}" for p in game.players.values()])
        text = (
            "👑 <b>LAST PERSON STANDING</b> 💀\n\n"
            "The ultimate test of endurance! Be one of the last three standing to win XP!\n\n"
            f"<b>Players ({len(game.players)}):</b>\n"
            f"{player_list}\n\n"
            f"Need at least {game.min_players_to_start} players to start. Game owner (@{html.escape(game.players[game.owner_id].username)}) can start."
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Join Game", callback_data="lps_join"),
                InlineKeyboardButton("🚪 Leave Game", callback_data="lps_leave"),
            ],
            [InlineKeyboardButton("▶️ Start Game", callback_data="lps_start_game")],
        ]
        return text, InlineKeyboardMarkup(keyboard)
    
    elif game.status == GameStatus.RUNNING:
        player_list = "\n".join([f" - @{html.escape(p.username)}" for p in game.players.values()])
        eliminated_list = "\n".join([f" - @{html.escape(p.username)}" for p in game.eliminated_players]) or "None yet."
        
        text = (
            "👑 <b>LAST PERSON STANDING</b> 💀\n\n"
            f"<b>Players Remaining ({game.get_remaining_players_count()}):</b>\n"
            f"{player_list}\n\n"
            f"<b>Eliminated:</b>\n"
            f"{eliminated_list}"
        )
        return text, None # No keyboard during running phase, eliminations are automatic
    
    elif game.status == GameStatus.FINISHED:
        winners = game.get_winners() # This will be empty if game.status was set to FINISHED without passing through the winner check
        if not winners: # Recalculate winners if status was set externally
            winners = list(game.players.values())
        
        winner_usernames = [f"@{html.escape(w.username)}" for w in winners]
        text = (
            f"🎉 <b>GAME OVER!</b> 🎉\n"
            f"The winners are: {', '.join(winner_usernames)}!\n"
            f"Each receives {XP_AWARD_PER_WINNER} XP!"
        )
        keyboard = [[InlineKeyboardButton("Play Again", callback_data="lps_new_lobby")]] # Option to start a new game
        return text, InlineKeyboardMarkup(keyboard)

    return "Unknown game state.", None
