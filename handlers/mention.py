from telegram import Update
from telegram.ext import CallbackContext
import structlog

logger = structlog.get_logger(__name__)

async def mention_handler(update: Update, context: CallbackContext) -> None:
    """Responds when the bot is mentioned."""
    logger.info("Bot was mentioned", chat_id=update.effective_chat.id)
    await update.message.reply_text("Hello! You mentioned me.")
