import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update
from telegram.ext import CallbackContext
from handlers import core
import database

@pytest.fixture
def mock_context_with_admin():
    """Fixture for a mock CallbackContext object with bot.get_chat_administrators mocked."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.args = []
    
    # Mock context.bot and its methods for the is_admin decorator
    context.bot = AsyncMock()
    # Mock get_chat_administrators to return the effective user as an admin by default
    admin_member = MagicMock()
    admin_member.user.id = 123 # Assuming 123 is the default effective_user.id for admin tests
    context.bot.get_chat_administrators.return_value = [admin_member]

    return context

@pytest.fixture
def mock_context_non_admin():
    """Fixture for a mock CallbackContext object for a non-admin user."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.args = []
    
    context.bot = AsyncMock()
    # Mock get_chat_administrators to return other admins, but not the effective user
    other_admin = MagicMock()
    other_admin.user.id = 999
    context.bot.get_chat_administrators.return_value = [other_admin]

    return context

@pytest.mark.asyncio
async def test_start_command(mock_context_with_admin):
    """Test that the /start command replies with a welcome message."""
    # Arrange
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123 # Ensure user ID matches the mock admin
    update.effective_user.mention_html.return_value = "Test User"
    update.message = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group' # Assume group chat for decorator

    # Act
    await core.start(update, mock_context_with_admin)

    # Assert
    update.message.reply_html.assert_called_once()
    called_with_text = update.message.reply_html.call_args[0][0]
    assert "Welcome, Test User" in called_with_text



@pytest.mark.asyncio
async def test_leaderboard_command_default_limit(mock_context_with_admin, mocker):
    """Test the /leaderboard command uses default limit of 10."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'
    mock_context_with_admin.args = [] # Ensure args is empty for default limit
    mocker.patch('database.get_leaderboard', return_value=[])

    await core.leaderboard(update, mock_context_with_admin)

    database.get_leaderboard.assert_called_once_with(mock_context_with_admin.bot_data['db'], limit=10)

@pytest.mark.asyncio
async def test_leaderboard_command_with_valid_limit(mock_context_with_admin, mocker):
    """Test the /leaderboard command with a valid custom limit."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'
    mock_context_with_admin.args = ['25']
    mocker.patch('database.get_leaderboard', return_value=[])

    await core.leaderboard(update, mock_context_with_admin)

    database.get_leaderboard.assert_called_once_with(mock_context_with_admin.bot_data['db'], limit=25)

@pytest.mark.asyncio
async def test_leaderboard_command_with_invalid_limit(mock_context_with_admin, mocker):
    """Test the /leaderboard command with an invalid limit (> 100)."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'
    mock_context_with_admin.args = ['101']
    mock_get_leaderboard = mocker.patch('yunks_game_2_0_1.database.get_leaderboard')

    await core.leaderboard(update, mock_context_with_admin)

    mock_get_leaderboard.assert_not_called()
    update.message.reply_text.assert_called_once_with("Please provide a number between 1 and 100.")

@pytest.mark.asyncio
async def test_leaderboard_command_with_non_numeric_limit(mock_context_with_admin, mocker):
    """Test the /leaderboard command with a non-numeric limit."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'
    mock_context_with_admin.args = ['abc']
    mock_get_leaderboard = mocker.patch('yunks_game_2_0_1.database.get_leaderboard')

    await core.leaderboard(update, mock_context_with_admin)

    mock_get_leaderboard.assert_not_called()
    update.message.reply_text.assert_called_once_with("Usage: /leaderboard [number]. Please provide a valid number.")

@pytest.mark.asyncio
async def test_leaderboard_output_populated(mock_context_with_admin, mocker):
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'
    mock_context_with_admin.args = []
    mock_leaderboard_data = [('user1', 100), ('user2', 95)]
    mocker.patch('database.get_leaderboard', return_value=mock_leaderboard_data)

    await core.leaderboard(update, mock_context_with_admin)

    update.message.reply_html.assert_called_once()
    reply_text = update.message.reply_html.call_args[0][0]
    assert "🏆 <b>Top 10 Players</b>" in reply_text
    assert "🥇 @user1 - 100 XP" in reply_text
    assert "🥈 @user2 - 95 XP" in reply_text


@pytest.mark.asyncio
async def test_help_command(mock_context_with_admin):
    """Test that the /help command replies with the help message."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.callback_query = None
    update.effective_chat.type = 'group'

    await core.help_command(update, mock_context_with_admin)

    update.message.reply_html.assert_called_once()
    assert "Yunks Gamebot Guide" in update.message.reply_html.call_args[0][0]
