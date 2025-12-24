from telegram import Update
from telegram.ext import CallbackContext
import structlog

logger = structlog.get_logger(__name__)

async def strict_edit_message(context: CallbackContext, chat_id: int, message_id: int, text: str, **kwargs) -> None:
    """
    A wrapper for `edit_message_text` that catches the error when the message content
    is identical to the new content, preventing unnecessary API calls and exceptions.
    """
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
    except Exception as e:
        if "Message is not modified" in str(e):
            logger.warning("Tried to edit a message with the same content.", exc_info=True)
        else:
            raise e
