import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update
from telegram.ext import CallbackContext
from yunks_game_2_0_1.handlers import messages
from yunks_game_2_0_1 import database

@pytest.mark.asyncio
async def test_handle_message_awards_xp(mocker):
    """Test that a regular message awards 1 XP."""
    # Arrange
    update = AsyncMock(spec=Update)
    update.effective_user.id = "test_user"
    update.effective_user.username = "test_username"
    update.message = AsyncMock()
    update.message.text = "This is a regular message."

    context = MagicMock(spec=CallbackContext)
    mock_db_client = MagicMock()
    context.bot_data = {'db': mock_db_client}

    mock_add_xp = mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

    # Act
    await messages.handle_message(update, context)

    # Assert
    mock_add_xp.assert_called_once_with(mock_db_client, "test_user", "test_username", 1)
