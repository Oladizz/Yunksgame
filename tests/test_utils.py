import pytest
from unittest.mock import AsyncMock, MagicMock
from yunks_game_2_0_1.handlers import utils
import telegram

@pytest.mark.asyncio
async def test_strict_edit_message_no_error():
    """Test the strict_edit_message function when there is no error."""
    context = MagicMock()
    context.bot = AsyncMock()
    chat_id = 12345
    message_id = 67890
    text = "Hello, world!"

    await utils.strict_edit_message(context, chat_id, message_id, text)

    context.bot.edit_message_text.assert_called_once_with(chat_id=chat_id, message_id=message_id, text=text)

@pytest.mark.asyncio
async def test_strict_edit_message_with_same_content_error():
    """Test the strict_edit_message function when there is a 'Message is not modified' error."""
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.edit_message_text.side_effect = telegram.error.BadRequest("Message is not modified")
    chat_id = 12345
    message_id = 67890
    text = "Hello, world!"

    await utils.strict_edit_message(context, chat_id, message_id, text)

    context.bot.edit_message_text.assert_called_once_with(chat_id=chat_id, message_id=message_id, text=text)

@pytest.mark.asyncio
async def test_strict_edit_message_with_other_error():
    """Test the strict_edit_message function when there is another error."""
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.edit_message_text.side_effect = telegram.error.BadRequest("Some other error")
    chat_id = 12345
    message_id = 67890
    text = "Hello, world!"

    with pytest.raises(telegram.error.BadRequest):
        await utils.strict_edit_message(context, chat_id, message_id, text)

    context.bot.edit_message_text.assert_called_once_with(chat_id=chat_id, message_id=message_id, text=text)
