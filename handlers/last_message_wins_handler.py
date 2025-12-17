import html
import asyncio
import time
from typing import Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import CallbackContext, JobQueue, MessageHandler, filters
import structlog

from .. import database as db
from ..game_logic.last_message_wins import LastMessageWinsGame, LastMessageWinsStatus
from .game_handler import strict_edit_message # Reusing strict_edit_message
from ..game_logic.player import Player # To get player data for XP handling

logger = structlog.get_logger(__name__)

LMW_COUNTDOWN_JOB_NAME = "lmw_countdown_job"
LMW_GAME_TIMEOUT_SECONDS = 120 # Max time a game can stay in LOBBY without starting

async def start_lmw_game(update: Update, context: CallbackContext) -> None:
    """Starts a new 'Last Message Wins' game lobby."""
    # This function can be called by a command (Update) or a button (CallbackQuery)
    if update.callback_query:
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
        reply_target = update.callback_query.message
    else:
        user = update.effective_user
        chat_id = update.effective_chat.id
        reply_target = update.message

    if 'last_message_wins_game' in context.chat_data:
        await reply_target.reply_text("A 'Last Message Wins' game is already in progress in this chat!")
        return

    logger.info("Starting new Last Message Wins game lobby", chat_id=chat_id, user_id=user.id)
    
    # Create a new game instance
    game = LastMessageWinsGame(chat_id=chat_id, owner_id=user.id)
    context.chat_data['last_message_wins_game'] = game

    # Render and send the lobby message
    text, keyboard = render_lmw_game(game)
    message = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='HTML')    
    
    # Save the message ID to the game state so we can edit it later
    game.game_message_id = message.message_id

    # Schedule lobby timeout (if no one starts the game)
    context.job_queue.run_once(
        lmw_lobby_timeout, 
        LMW_GAME_TIMEOUT_SECONDS, 
        data={'chat_id': chat_id, 'game_message_id': game.game_message_id},
        name=f"lmw_lobby_timeout_{chat_id}"
    )

async def lmw_lobby_timeout(context: CallbackContext) -> None:
    """Ends the LMW game if it stays in lobby too long."""
    chat_id = context.job.data['chat_id']
    game_message_id = context.job.data['game_message_id']
    game: LastMessageWinsGame = context.chat_data.get('last_message_wins_game')

    if game and game.status == LastMessageWinsStatus.LOBBY:
        await strict_edit_message(context, chat_id, game_message_id, "The 'Last Message Wins' lobby timed out due to inactivity.", None)
        context.chat_data.pop('last_message_wins_game', None)
        logger.info("LMW lobby timed out", chat_id=chat_id)

async def handle_lmw_callback(update: Update, context: CallbackContext) -> None:
    """The main handler for all 'Last Message Wins' game callbacks."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    db_client = context.bot_data['db']
    
    game: LastMessageWinsGame = context.chat_data.get('last_message_wins_game')
    if not game:
        await strict_edit_message(context, chat_id, query.message.message_id, "This game lobby has expired. Please start a new one.", None)
        return

    # Check if the game is in a valid state for this callback
    if game.status != LastMessageWinsStatus.LOBBY:
        await query.answer("The game has already started or finished.", show_alert=True)
        return
        
    # Only owner can start the game
    if query.data == 'lmw_start_game' and user.id != game.owner_id:
        await query.answer("Only the game owner can start the game.", show_alert=True)
        return

    if query.data == 'lmw_join':
        if user.id not in game.players:
            # Check if user has enough XP
            user_data = db.get_user_data(db_client, user.id)
            if not user_data or user_data.get('xp', 0) < game.entry_xp_cost:
                await query.answer(f"You need at least {game.entry_xp_cost} XP to join!", show_alert=True)
                return
            
            # Deduct XP and add to pool
            await db.add_xp(db_client, user.id, user.username, xp_to_add=-game.entry_xp_cost)
            game.add_player(user.id, user.username or f"user{user.id}")
            logger.info("Player joined LMW game", chat_id=chat_id, user_id=user.id, xp_cost=game.entry_xp_cost, current_pool=game.xp_pool)
            
            # Cancel lobby timeout if game can start (e.g. at least 1 player)
            for job in context.job_queue.get_jobs_by_name(f"lmw_lobby_timeout_{chat_id}"):
                job.schedule_removal()
        else:
            await query.answer("You have already joined this game.", show_alert=True)
            return
    
    elif query.data == 'lmw_leave':
        if user.id in game.players:
            # Refund XP and remove player
            await db.add_xp(db_client, user.id, user.username, xp_to_add=game.entry_xp_cost)
            game.remove_player(user.id)
            logger.info("Player left LMW game", chat_id=chat_id, user_id=user.id, xp_refund=game.entry_xp_cost, current_pool=game.xp_pool)
        else:
            await query.answer("You are not in this game.", show_alert=True)
            return

    elif query.data == 'lmw_start_game':
        if len(game.players) < 2:
            await query.answer("You need at least 2 players to start the game.", show_alert=True)
            return
        
        # Cancel lobby timeout
        for job in context.job_queue.get_jobs_by_name(f"lmw_lobby_timeout_{chat_id}"):
            job.schedule_removal()

        if game.start_countdown():
            logger.info("LMW game started countdown", chat_id=chat_id, pool=game.xp_pool)
            await context.bot.send_message(chat_id=chat_id, text=f"🔥 <b>LAST MESSAGE WINS!</b> 🔥\n\nStarting in {game.countdown_total} seconds! Send your single message NOW!\n\n💰 Current XP Pool: <b>{game.xp_pool} XP</b>", parse_mode='HTML')
            
            # Schedule the countdown check job
            context.job_queue.run_repeating(
                check_lmw_countdown, 
                interval=1, # Check every second
                first=1, # Start after 1 second
                data={'chat_id': chat_id, 'game_message_id': game.game_message_id},
                name=LMW_COUNTDOWN_JOB_NAME
            )
        else:
            await query.answer("Failed to start game. Is it in the lobby state and are there players?", show_alert=True)
            return

    # Re-render the game message with the new state
    text, keyboard = render_lmw_game(game)
    await strict_edit_message(context, chat_id, query.message.message_id, text, keyboard)


async def handle_lmw_message(update: Update, context: CallbackContext) -> None:
    """Handles incoming messages for the 'Last Message Wins' game."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    message_text = update.message.text
    
    game: LastMessageWinsGame = context.chat_data.get('last_message_wins_game')

    if not game or game.chat_id != chat_id or game.status != LastMessageWinsStatus.COUNTDOWN:
        return # Not an active game in this chat or not in countdown phase

    if user.id not in game.players:
        try:
            await update.message.delete()
        except error.BadRequest as e:
            logger.warning("Could not delete message (not in game)", chat_id=chat_id, message_id=update.message.message_id, error=e)
        await context.bot.send_message(chat_id=chat_id, text=f"{user.mention_html()}, you are not in the game! Join first!", parse_mode='HTML')
        return

    if game.record_message(user.id, user.username or f"user{user.id}", update.message.message_id):
        logger.info("Recorded valid LMW message", chat_id=chat_id, user_id=user.id, message_id=update.message.message_id)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ {user.mention_html()} recorded a valid message!", parse_mode='HTML')
    else:
        try:
            await update.message.delete()
        except error.BadRequest as e:
            logger.warning("Could not delete message (already sent one)", chat_id=chat_id, message_id=update.message.message_id, error=e)
        await context.bot.send_message(chat_id=chat_id, text=f"🚫 {user.mention_html()}, you can only send ONE message!", parse_mode='HTML')
    

async def check_lmw_countdown(context: CallbackContext) -> None:
    """Periodically checks the LMW game countdown and determines the winner."""
    chat_id = context.job.data['chat_id']
    game_message_id = context.job.data['game_message_id']
    game: LastMessageWinsGame = context.chat_data.get('last_message_wins_game')

    if not game or game.status != LastMessageWinsStatus.COUNTDOWN:
        logger.info("LMW countdown job finished/stopped as game is not active or not in countdown.", chat_id=chat_id)
        context.job.schedule_removal() # Stop this job
        return

    remaining_time = int(game.countdown_end_time - time.time())
    
    if remaining_time <= 0:
        winner_info = game.determine_winner()
        
        if winner_info:
            winner_user_id = winner_info['user_id']
            winner_username = winner_info['username']
            winner_message_id = winner_info['message_id']
            
            # Award XP
            db_client = context.bot_data['db']
            await db.add_xp(db_client, winner_user_id, winner_username, xp_to_add=game.xp_pool)
            
            # Send winner message
            winner_message = (
                f"🎉 <b>TIME'S UP!</b> 🎉\n\n"
                f"The last message sender is {html.escape(winner_username)}!\n"
                f"Congratulations, you won <b>{game.xp_pool} XP</b>!"
            )
            await context.bot.send_message(chat_id=chat_id, text=winner_message, parse_mode='HTML')
            
            # Optionally highlight the winning message (requires message_id and chat_id)
            try:
                await context.bot.pin_chat_message(chat_id=chat_id, message_id=winner_message_id, disable_notification=True)
                await asyncio.sleep(5) # Keep pinned for a few seconds
                await context.bot.unpin_chat_message(chat_id=chat_id, message_id=winner_message_id)
            except Exception as e:
                logger.warning("Could not pin/unpin winning message", chat_id=chat_id, message_id=winner_message_id, error=e)
            
            logger.info("LMW game finished, winner awarded XP", chat_id=chat_id, winner_id=winner_user_id, xp_awarded=game.xp_pool)
        else:
            await context.bot.send_message(chat_id=chat_id, text="😔 Time's up, but no valid messages were sent! No winner this round.")
            logger.info("LMW game finished, no winner", chat_id=chat_id)
            
        context.chat_data.pop('last_message_wins_game', None) # Clear game state
        context.job.schedule_removal() # Stop this job
        
    elif remaining_time % 10 == 0 or remaining_time <= 5: # Announce every 10s and last 5s
        await strict_edit_message(context, chat_id, game_message_id, render_lmw_game(game)[0], render_lmw_game(game)[1])


def render_lmw_game(game: LastMessageWinsGame) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Renders the game message text and keyboard based on the current game state.
    """
    if game.status == LastMessageWinsStatus.LOBBY:
        player_list = "\n".join([f" - @{html.escape(username)}" for username in game.players.values()])
        text = (
            "⏳ <b>LAST MESSAGE WINS!</b> 🏆\n\n"
            f"The last person to send a message before the timer runs out wins the entire XP pool!\n"
            f"💰 Entry Fee: <b>{game.entry_xp_cost} XP</b>\n"
            f"Current XP Pool: <b>{game.xp_pool} XP</b>\n\n"
            f"<b>Players ({len(game.players)}):</b>\n"
            f"{player_list if player_list else 'No players yet.'}\n\n"
            f"Game owner (@{html.escape(game.players.get(game.owner_id, 'Unknown'))}) can start."
        )
        keyboard = [
            [
                InlineKeyboardButton(f"➕ Join ({game.entry_xp_cost} XP)", callback_data="lmw_join"),
                InlineKeyboardButton("🚪 Leave", callback_data="lmw_leave"),
            ],
            [InlineKeyboardButton("▶️ Start Game", callback_data="lmw_start_game")],
        ]
        return text, InlineKeyboardMarkup(keyboard)
    
    elif game.status == LastMessageWinsStatus.COUNTDOWN:
        remaining_time = int(game.countdown_end_time - time.time()) if game.countdown_end_time else 0
        last_msg_user = game.last_valid_message['username'] if game.last_valid_message else 'None yet'
        
        text = (
            "⏳ <b>LAST MESSAGE WINS!</b> 🏆\n\n"
            f"Time Left: <b>{max(0, remaining_time)} seconds</b>\n"
            f"💰 Current XP Pool: <b>{game.xp_pool} XP</b>\n"
            f"Last valid message by: <b>@{html.escape(last_msg_user)}</b>\n\n"
            "Send your message now!"
        )
        return text, None # No interactive keyboard during countdown

    elif game.status == LastMessageWinsStatus.FINISHED:
        winner_info = game.last_valid_message
        winner_text = f"The winner is @{html.escape(winner_info['username'])} with {game.xp_pool} XP!" if winner_info else "No winner this round."
        
        text = (
            f"🎉 <b>GAME OVER!</b> 🎉\n\n"
            f"{winner_text}"
        )
        keyboard = [[InlineKeyboardButton("Play Again", callback_data="lmw_new_lobby")]] 
        return text, InlineKeyboardMarkup(keyboard)

    return "Unknown game state.", None
