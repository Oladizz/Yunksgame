import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog
from .. import database as db # Assuming database is needed for profile/leaderboard
from . import core, game_guess_number, lastman_game, last_message_wins_game # Import core handlers for start, leaderboard
import structlog

logger = structlog.get_logger(__name__)

async def button_handler(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and calls the appropriate handler."""
    query = update.callback_query
    await query.answer()

    if query.data == 'leaderboard':
        # Pass the update and context to the core.leaderboard handler
        # The leaderboard handler is designed to handle both commands and callbacks
        await core.leaderboard(update, context)
    elif query.data == 'start_menu':
        # Pass the update and context to the core.start handler
        await core.start(update, context)
    # Add other button handlers here as features are implemented
    elif query.data == 'profile':
        await core.user_profile(update, context)
    elif query.data == 'game_menu':
        keyboard = [
            [InlineKeyboardButton("🔢 Guess the Number", callback_data='start_number_game')],
            [InlineKeyboardButton("🏆 Last Person Standing", callback_data='start_lastman_game')],
            [InlineKeyboardButton("✉️ Last Message Wins", callback_data='start_lmw_game')],
            [InlineKeyboardButton("« Back to Main Menu", callback_data='start_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("Please choose a game to play:", reply_markup=reply_markup)
    elif query.data == 'help_menu':
        await core.help_command(update, context)
    elif query.data == 'start_number_game':
        await game_guess_number.start_new_game(update, context)
    elif query.data == 'start_lastman_game':
        await lastman_game.start_lastman_lobby(update, context)
    elif query.data == 'start_lmw_game':
        await last_message_wins_game.start_lmw_lobby(update, context)
    else:
        await query.message.edit_text("Unknown action.")