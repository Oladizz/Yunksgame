import html
from typing import Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
import structlog
from Yunks_game import database as db
from Yunks_game import game
from Yunks_game.handlers import core # Import core handlers for help_command
from Yunks_game.handlers.game_handler import strict_edit_message

logger = structlog.get_logger(__name__)

async def button_handler(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and calls the appropriate handler."""
    query = update.callback_query
    await query.answer() 
    
    user_id = query.from_user.id
    db_client = context.bot_data['db']
    logger.info("button_handler", user_id=user_id, data=query.data)

    if query.data == 'profile':
        user_data = db.get_user_data(db_client, user_id)
        if user_data:
            username = user_data.get('username', 'N/A')
            xp = user_data.get('xp', 0)
            profile_text = (
                f"👤 <b>Your Profile</b>\n\n"
                f"✨ <b>Username:</b> @{username}\n"
                f"🌟 <b>XP:</b> {xp}"
            )
            await strict_edit_message(context, query.message.chat_id, query.message.message_id, profile_text, None, parse_mode='HTML')
        else:
            await strict_edit_message(context, query.message.chat_id, query.message.message_id, "You don't have a profile yet. Send some messages to start!", None, parse_mode='HTML')

    elif query.data == 'leaderboard':
        leaderboard_data = db.get_leaderboard(db_client)
        if not leaderboard_data:
            await strict_edit_message(context, query.message.chat_id, query.message.message_id, "The leaderboard is currently empty. Start sending messages to get on it!", None, parse_mode='HTML')
            return

        leaderboard_text = "🏆 <b>Top 10 Players</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (username, xp) in enumerate(leaderboard_data):
            place = f"{medals[i]} " if i < 3 else f"  {i+1}. "
            leaderboard_text += f"{place} @{html.escape(username)} - {xp} XP\n"
        
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, leaderboard_text, None, parse_mode='HTML')

    elif query.data == 'game_menu':
        keyboard = [
            [InlineKeyboardButton("🔢 Guess the Number", callback_data='start_number_game')],
            [InlineKeyboardButton("🐀 Rat in the Farm", callback_data='start_rat_game')],
            [InlineKeyboardButton("🧍 Last Person Standing", callback_data='start_lps_game')],
            [InlineKeyboardButton("⏳ Last Message Wins", callback_data='start_lmw_game')], # New game button
            [InlineKeyboardButton("« Back to Main Menu", callback_data='start')], # Assuming 'start' takes them back
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, "Please choose a game to play:", reply_markup, parse_mode='HTML')

    elif query.data == 'start_number_game':
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, "Starting 'Guess the Number'...", None, parse_mode='HTML')
        # The game.start_new_game expects an `update` object with a `message` attribute
        await game.start_new_game(update, context)

    elif query.data == 'start_rat_game':
        await core.start_farm_game(update, context)
    
    elif query.data == 'start_lps_game': # New handler for LPS game
        from Yunks_game.handlers import last_person_standing_handler # Import here to avoid circular dependency
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, "Starting 'Last Person Standing'...", None, parse_mode='HTML')
        await last_person_standing_handler.start_lps_game(update, context)
    
    elif query.data == 'start_lmw_game': # New handler for LMW game
        from Yunks_game.handlers import last_message_wins_handler # Import here to avoid circular dependency
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, "Starting 'Last Message Wins'...", None, parse_mode='HTML')
        await last_message_wins_handler.start_lmw_game(update, context)
        
    elif query.data == 'help_menu':
        await core.help_command(update, context) # Use core.help_command
    
    elif query.data == 'start': # Handler to go back to the main menu
        await core.start(update, context)

    else:
        await strict_edit_message(context, query.message.chat_id, query.message.message_id, "Unknown action.", None, parse_mode='HTML')

MAX_LEADERBOARD_LIMIT = 100

async def leaderboard_command(update: Update, context: CallbackContext) -> None:
    """Displays the leaderboard, optionally up to a specified number of players."""
    db_client = context.bot_data['db']
    limit = 10 # Default limit
    
    if context.args:
        try:
            requested_limit = int(context.args[0])
            if 1 <= requested_limit <= MAX_LEADERBOARD_LIMIT:
                limit = requested_limit
            else:
                await update.message.reply_text(f"Please provide a number between 1 and {MAX_LEADERBOARD_LIMIT}.")
                return
        except ValueError:
            await update.message.reply_text("Usage: /leaderboard [number]. Please provide a valid number.")
            return

    leaderboard_data = db.get_leaderboard(db_client, limit=limit)
    if not leaderboard_data:
        await update.message.reply_text("The leaderboard is currently empty. Start sending messages to get on it!")
        return

    leaderboard_text = f"🏆 <b>Top {limit} Players</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, xp) in enumerate(leaderboard_data):
        place = f"{medals[i]} " if i < 3 else f"  {i+1}. "
        leaderboard_text += f"{place} @{html.escape(username)} - {xp} XP\n"
    
    await update.message.reply_html(leaderboard_text)
    logger.info("Leaderboard requested", user_id=update.effective_user.id, limit=limit)
