import pytest
from unittest.mock import AsyncMock, MagicMock
from yunks_game_2_0_1.handlers import mention

@pytest.mark.asyncio
async def test_mention_handler():
    """Test the mention handler."""
    update = AsyncMock()
    update.message = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    context = MagicMock()

    await mention.mention_handler(update, context)

    update.message.reply_text.assert_called_once_with("Hello! You mentioned me.")
