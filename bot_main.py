import os
import sys # Added for sys.path modification
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
import structlog
import telegram
import asyncio

from Yunks_game import database
from Yunks_game import game # For "Guess the Number"
from Yunks_game.handlers import core, messages, callbacks, actions, game_handler, admin, last_person_standing_handler, last_message_wins_handler
from Yunks_game.logging_config import setup_logging

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

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    # Load environment variables from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(script_dir, '.env')
    load_dotenv(dotenv_path)
    
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
        logger.error("Firebase credentials not found! Please set either 'FIREBASE_CREDENTIALS' (JSON content) or 'FIREBASE_CREDENTIALS_PATH' (file path) in your .env file or environment.")
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
    application.add_handler(CommandHandler("help", core.help_command))
    application.add_handler(CommandHandler("start_game", game.start_new_game)) # For "Guess the Number"
    application.add_handler(CommandHandler("farm", core.start_farm_game))      # For "Rat in the Farm"
    application.add_handler(CommandHandler("lastman", last_person_standing_handler.start_lps_game)) # For "Last Person Standing"
    application.add_handler(CommandHandler("lmw", last_message_wins_handler.start_lmw_game)) # For "Last Message Wins"
    application.add_handler(CommandHandler("steal", actions.steal_xp))
    application.add_handler(CommandHandler("give", actions.give_xp))
    application.add_handler(CommandHandler("awardxp", admin.award_xp))
    application.add_handler(CommandHandler("endgame", admin.end_game_command))
    application.add_handler(CommandHandler("leaderboard", callbacks.leaderboard_command))

    # Register callback query handlers
    # One for the main menu, and one for the farm game, and one for last person standing game
    application.add_handler(CallbackQueryHandler(callbacks.button_handler, pattern='^(start|profile|leaderboard|game_menu|help_menu|start_number_game|start_rat_game|start_lps_game|start_lmw_game)$'))
    application.add_handler(CallbackQueryHandler(game_handler.handle_game_callback, pattern='^ratgame_'))
    application.add_handler(CallbackQueryHandler(last_person_standing_handler.handle_lps_callback, pattern='^lps_'))
    application.add_handler(CallbackQueryHandler(last_message_wins_handler.handle_lmw_callback, pattern='^lmw_'))

    # Register message handler for XP and game guesses
    # This needs to be ordered carefully: general messages at the end, game-specific messages earlier
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, last_message_wins_handler.handle_lmw_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_message))

    # Register a handler for unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, messages.unknown_command))

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