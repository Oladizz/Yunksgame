import structlog
from telegram import Update
from telegram.ext import CallbackContext
from .. import database as db
from .. import game

logger = structlog.get_logger(__name__)

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handles regular messages and adds XP."""
    user = update.effective_user
    db_client = context.bot_data['db']

    # Check for bot mention first
    if update.message and update.message.text:
        bot_username = context.bot.username
        if bot_username and bot_username in update.message.text:
            await on_bot_mention(update, context)
            return # Stop further processing

    if user and update.message and not update.message.text.startswith('/'):
        # Check if user is in a game
        if 'game' in context.user_data and update.message.text.isdigit():
            logger.info("User is in a game, handling guess", user_id=user.id, message_text=update.message.text)
            await game.handle_guess(update, context)
        else:
            logger.info("handle_message", user_id=user.id, username=user.username)
            db.add_xp(db_client, user.id, user.username)

async def unknown_command(update: Update, context: CallbackContext):
    """Handles unknown commands."""
    logger.warning("unknown_command", command=update.message.text)
    await update.message.reply_text("Sorry, I didn't understand that command.")

async def on_bot_mention(update: Update, context: CallbackContext) -> None:
    """Replies when the bot is mentioned."""
    bot_username = context.bot.username
    if bot_username and bot_username in update.message.text:
        await update.message.reply_text("I am Yunks gamebot! Use /start to start me.")
        logger.info("Bot mentioned", user_id=update.effective_user.id, message_text=update.message.text)
