import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update
from telegram.ext import CallbackContext
from yunks_game_2_0_1.handlers import decorators

@pytest.fixture
def mock_update_private():
    """Mock Update object for a private chat."""
    update = AsyncMock(spec=Update)
    update.effective_chat.type = 'private'
    update.effective_user.id = 123
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_update_group_admin():
    """Mock Update object for a group chat with an admin user."""
    update = AsyncMock(spec=Update)
    update.effective_chat.type = 'group'
    update.effective_user.id = 123 # This user is an admin
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_update_group_non_admin():
    """Mock Update object for a group chat with a non-admin user."""
    update = AsyncMock(spec=Update)
    update.effective_chat.type = 'group'
    update.effective_user.id = 456 # This user is NOT an admin
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.bot = AsyncMock()
    context.bot.get_chat_administrators = AsyncMock()
    return context

@pytest.mark.asyncio
async def test_is_admin_private_chat_passes(mock_update_private, mock_context):
    """Test that the decorator always passes in a private chat."""
    mock_func = AsyncMock()
    wrapped_func = decorators.is_admin(mock_func)
    
    await wrapped_func(mock_update_private, mock_context)
    
    mock_func.assert_called_once_with(mock_update_private, mock_context)
    mock_context.bot.get_chat_administrators.assert_not_called()

@pytest.mark.asyncio
async def test_is_admin_group_admin_passes(mock_update_group_admin, mock_context):
    """Test that the decorator passes for an admin in a group chat."""
    # Mock get_chat_administrators to return the effective user as an admin
    admin_member = MagicMock()
    admin_member.user.id = mock_update_group_admin.effective_user.id
    mock_context.bot.get_chat_administrators.return_value = [admin_member]

    mock_func = AsyncMock()
    wrapped_func = decorators.is_admin(mock_func)
    
    await wrapped_func(mock_update_group_admin, mock_context)
    
    mock_func.assert_called_once_with(mock_update_group_admin, mock_context)
    mock_context.bot.get_chat_administrators.assert_called_once()

@pytest.mark.asyncio
async def test_is_admin_group_non_admin_fails(mock_update_group_non_admin, mock_context):
    """Test that the decorator fails for a non-admin in a group chat."""
    # Mock get_chat_administrators to return other admins, but not the effective user
    other_admin = MagicMock()
    other_admin.user.id = 999
    mock_context.bot.get_chat_administrators.return_value = [other_admin]

    mock_func = AsyncMock()
    wrapped_func = decorators.is_admin(mock_func)
    
    await wrapped_func(mock_update_group_non_admin, mock_context)
    
    mock_func.assert_not_called()
    mock_context.bot.get_chat_administrators.assert_called_once()
    mock_update_group_non_admin.message.reply_text.assert_called_once_with("This command can only be used by group admins.")
