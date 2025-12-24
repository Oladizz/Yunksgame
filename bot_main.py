import os
import sys
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
import structlog
import telegram
import asyncio

from yunks_game_2_0_1 import database
from yunks_game_2_0_1.handlers import core, messages, actions, game_guess_number, lastman_game, game_lmw, mention
from yunks_game_2_0_1.logging_config import setup_logging

# Set up logging
setup_logging()
logger = structlog.get_logger(__name__)

async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and handle flood control."""
    if isinstance(context.error, telegram.error.RetryAfter):
        logger.warning(
            "Flood control exceeded. Suggested retry in %s seconds. Pausing...",
            context.error.retry_after,
            update=update
        )
        await asyncio.sleep(context.error.retry_after)
        return
    
    logger.error("Exception while handling an update:", exc_info=context.error)

async def main_message_handler(update: Update, context: CallbackContext) -> None:
    """Route messages to the correct handler (game or standard)."""
    logger.info("Main message handler received update")
    if 'game' in context.user_data:
        logger.info("Routing to guess the number game handler")
        await game_guess_number.handle_guess(update, context)
    elif 'lmw_game' in context.chat_data and context.chat_data['lmw_game']['status'] == 'in_progress':
        logger.info("Routing to lmw game handler")
        await game_lmw.handle_lmw_message(update, context)
    else:
        logger.info("Routing to standard message handler")
        await messages.handle_message(update, context)

async def button_handler(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and calls the appropriate handler."""
    query = update.callback_query
    logger.info("Button handler received query", data=query.data)
    await query.answer()

    if query.data == 'leaderboard':
        logger.info("Calling leaderboard handler")
        # Pass the update and context to the core.leaderboard handler
        # The leaderboard handler is designed to handle both commands and callbacks
        await core.leaderboard(update, context)
    elif query.data == 'start_menu':
        logger.info("Calling start_menu handler")
        # Pass the update and context to the core.start handler
        await core.start(update, context)
    # Add other button handlers here as features are implemented
    elif query.data == 'profile':
        logger.info("Calling profile handler")
        await core.user_profile(update, context)
    elif query.data == 'game_menu':
        logger.info("Calling game_menu handler")
        keyboard = [
            [InlineKeyboardButton("🔢 Guess the Number", callback_data='start_number_game')],
            [InlineKeyboardButton("🏆 Last Message Wins", callback_data='lmw_game')],
            [InlineKeyboardButton("👑 Last Man Standing", callback_data='lastman_game')], # New button
            [InlineKeyboardButton("« Back to Main Menu", callback_data='start_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("Please choose a game to play:", reply_markup=reply_markup)
    elif query.data == 'help_menu':
        logger.info("Calling help_menu handler")
        await core.help_command(update, context)
    elif query.data == 'start_number_game':
        logger.info("Calling start_number_game handler")
        await game_guess_number.start_new_game(update, context)
    elif query.data == 'lmw_game':
        logger.info("Calling lmw_game handler")
        await game_lmw.start_lmw_lobby(update, context)
    elif query.data == 'lastman_game': # New callback handler
        logger.info("Calling lastman_game handler")
        await lastman_game.start_lastman_lobby(update, context)
    else:
        logger.info("Unknown action")
        await query.message.edit_text("Unknown action.")


def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    # Load environment variables from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(script_dir, '.env')
    load_dotenv(dotenv_path)
    
    token = os.getenv('TELEGRAM_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')
    port = int(os.getenv('PORT', '8000'))
    # Determine Firebase credentials source
    firebase_credentials_data = None
    is_json_string = False

    firebase_credentials_env = os.getenv('FIREBASE_CREDENTIALS')
    if firebase_credentials_env:
        firebase_credentials_data = firebase_credentials_env
        is_json_string = True
        logger.info("Using Firebase credentials from environment variable 'FIREBASE_CREDENTIALS'.")
    else:
        firebase_credentials_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
        if firebase_credentials_path:
            firebase_credentials_data = firebase_credentials_path
            logger.info(f"Using Firebase credentials from path: {firebase_credentials_path}")
        
    if not token:
        logger.error("TELEGRAM_TOKEN not found! Please add it to your .env file or environment.")
        return
    if not firebase_credentials_data:
        logger.error("Firebase credentials not found! Please set either 'FIREBASE_CREDENTIALS' (JSON content) or 'FIREBASE_CREDENTIALS_PATH' (file file) in your .env file or environment.")
        return

    # Initialize Firebase
    db_client = database.init_firebase(firebase_credentials_data, is_json_string=is_json_string)
    if not db_client:
        logger.error("Failed to initialize Firebase. Exiting.")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()
    application.bot_data['db'] = db_client

    # Register the error handler
    application.add_error_handler(error_handler)

    # Register command handlers
    application.add_handler(CommandHandler("start", core.start))
    application.add_handler(CommandHandler("leaderboard", core.leaderboard))
    application.add_handler(CommandHandler("profile", core.user_profile))
    application.add_handler(CommandHandler("menu", core.user_profile))
    application.add_handler(CommandHandler("give", actions.give_xp))
    application.add_handler(CommandHandler("steal", actions.steal_xp))
    application.add_handler(CommandHandler("start_game", game_guess_number.start_new_game))
    application.add_handler(CommandHandler("help", core.help_command))
    application.add_handler(CommandHandler("awardxp", actions.award_xp))
    application.add_handler(CommandHandler("endgame", actions.end_game))
    application.add_handler(CommandHandler("lastman", lastman_game.start_lastman_lobby))
    application.add_handler(CommandHandler("lmw", game_lmw.start_lmw_lobby))


    # Register callback query handler
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(leaderboard|start_menu|profile|game_menu|start_number_game|help_menu|lmw_game|lastman_game)$'))
    application.add_handler(CallbackQueryHandler(lastman_game.lastman_callback_handler, pattern='^(lastman_join|lastman_start)$'))
    application.add_handler(CallbackQueryHandler(game_lmw.lmw_callback_handler, pattern='^(lmw_join|lmw_start)$'))

    # Register message handler for XP and game guesses
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
    application.add_handler(MessageHandler(filters.Entity(telegram.constants.MessageEntityType.MENTION), mention.mention_handler))

    # Run the bot
    if webhook_url:
        logger.info("Bot is starting with webhook...", port=port)
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{webhook_url}/{token}"
        )
        logger.info("Bot is listening for webhooks", port=port)
    else:
        logger.info("Bot is starting with polling...")
        application.run_polling()
    
    logger.info("Bot has stopped.")

if __name__ == '__main__':
    main()
