from telegram import Update
from telegram.ext import CallbackContext
import structlog
from .. import database as db

logger = structlog.get_logger(__name__)

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handles regular messages and adds XP."""
    user = update.effective_user
    if not user:
        return

    # Ignore commands
    if update.message and update.message.text and update.message.text.startswith('/'):
        return

    logger.info("handle_message: Awarding XP", user_id=user.id, username=user.username)
    db_client = context.bot_data['db']
    await db.add_xp(db_client, user.id, user.username, 1)
