import os
import sys
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
import structlog
import telegram
import asyncio

# Add the directory containing 'yunks_game_2_0_1' to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunks_game_2_0_1 import database
from yunks_game_2_0_1.handlers import core, messages, actions, callbacks, game_guess_number, lastman_game, last_message_wins_game
from yunks_game_2_0_1.logging_config import setup_logging

# Set up logging
yunks_game_2_0_1.logging_config.setup_logging()
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
    if 'game' in context.user_data:
        await game_guess_number.handle_guess(update, context)
    elif 'lmw_game' in context.chat_data and context.chat_data['lmw_game']['status'] == 'in_progress':
        await last_message_wins_game.lmw_message_handler(update, context)
    else:
        await messages.handle_message(update, context)

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    # Load environment variables from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(script_dir, '.env')
    load_dotenv(dotenv_path=dotenv_path, override=True)
    
    token = os.getenv('TELEGRAM_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')
    port = int(os.getenv('PORT', '8443'))
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
    application.add_handler(CommandHandler("lmw", last_message_wins_game.start_lmw_lobby))


    # Register callback query handler
    application.add_handler(CallbackQueryHandler(callbacks.button_handler, pattern='^(leaderboard|start_menu|profile|game_menu|start_number_game|help_menu|start_lastman_game|start_lmw_game)$'))
    application.add_handler(CallbackQueryHandler(lastman_game.lastman_callback_handler, pattern='^(lastman_join|lastman_start)$'))
    application.add_handler(CallbackQueryHandler(last_message_wins_game.lmw_callback_handler, pattern='^(lmw_join|lmw_start)$'))

    # Register message handler for XP and game guesses
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))

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
