import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from yunks_game_2_0_1.handlers import callbacks, core, game_guess_number
from yunks_game_2_0_1 import database

@pytest.fixture
def mock_update_callback():
    """Fixture for a mock Update object with a callback query."""
    update = AsyncMock(spec=Update)
    update.callback_query = AsyncMock()
    update.effective_user.id = 123
    update.callback_query.from_user.id = 123
    update.callback_query.message = AsyncMock()
    update.callback_query.message.edit_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.type = 'group'
    return update

@pytest.fixture
def mock_context_with_admin():
    """Fixture for a mock CallbackContext object with bot.get_chat_administrators mocked."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.args = []
    
    context.bot = AsyncMock()
    admin_member = MagicMock()
    admin_member.user.id = 123
    context.bot.get_chat_administrators.return_value = [admin_member]

    return context

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.core.leaderboard', new_callable=AsyncMock)
async def test_button_handler_leaderboard(mock_leaderboard, mock_update_callback):
    """Test that the button_handler calls core.leaderboard for 'leaderboard' data."""
    mock_update_callback.callback_query.data = 'leaderboard'
    
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = AsyncMock()
    admin_member = MagicMock()
    admin_member.user.id = 123
    mock_context.bot.get_chat_administrators.return_value = [admin_member]

    await callbacks.button_handler(mock_update_callback, mock_context)
    
    mock_update_callback.callback_query.answer.assert_called_once()
    mock_leaderboard.assert_called_once()

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.core.start', new_callable=AsyncMock)
async def test_button_handler_start_menu(mock_start, mock_update_callback):
    """Test that the button_handler calls core.start for 'start_menu' data."""
    mock_update_callback.callback_query.data = 'start_menu'

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = AsyncMock()
    admin_member = MagicMock()
    admin_member.user.id = 123
    mock_context.bot.get_chat_administrators.return_value = [admin_member]
    
    await callbacks.button_handler(mock_update_callback, mock_context)
    
    mock_update_callback.callback_query.answer.assert_called_once()
    mock_start.assert_called_once()

@pytest.mark.asyncio
async def test_button_handler_profile_user_exists(mock_update_callback, mock_context_with_admin, mocker):
    """Test the profile button when the user exists."""
    mock_update_callback.callback_query.data = 'profile'
    
    mocker.patch('yunks_game_2_0_1.database.get_user_data', return_value={'username': 'testuser', 'xp': 120})

    await callbacks.button_handler(mock_update_callback, mock_context_with_admin)
    
    database.get_user_data.assert_called_once_with(mock_context_with_admin.bot_data['db'], 123)
    mock_update_callback.callback_query.message.edit_text.assert_called_once()
    reply_text = mock_update_callback.callback_query.message.edit_text.call_args.kwargs['text']
    assert "Your Profile" in reply_text
    assert "testuser" in reply_text
    assert "120" in reply_text

@pytest.mark.asyncio
async def test_button_handler_profile_no_user(mock_update_callback, mock_context_with_admin, mocker):
    """Test the profile button when the user does not exist."""
    mock_update_callback.callback_query.data = 'profile'
    
    mocker.patch('yunks_game_2_0_1.database.get_user_data', return_value=None)

    await callbacks.button_handler(mock_update_callback, mock_context_with_admin)
    
    database.get_user_data.assert_called_once_with(mock_context_with_admin.bot_data['db'], 123)
    mock_update_callback.callback_query.message.edit_text.assert_called_once()
    assert "You don't have a profile yet" in mock_update_callback.callback_query.message.edit_text.call_args.kwargs['text']

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.core.help_command', new_callable=AsyncMock)
async def test_button_handler_help_menu(mock_help_command, mock_update_callback, mock_context_with_admin):
    """Test that the help button calls core.help_command."""
    mock_update_callback.callback_query.data = 'help_menu'

    await callbacks.button_handler(mock_update_callback, mock_context_with_admin)
    
    mock_update_callback.callback_query.answer.assert_called_once()
    mock_help_command.assert_called_once()

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.game_guess_number.start_new_game', new_callable=AsyncMock)
async def test_button_handler_start_number_game(mock_start_new_game, mock_update_callback, mock_context_with_admin):
    """Test that the 'Guess the Number' button starts a new game."""
    mock_update_callback.callback_query.data = 'start_number_game'

    await callbacks.button_handler(mock_update_callback, mock_context_with_admin)

    mock_update_callback.callback_query.answer.assert_called_once()
    mock_start_new_game.assert_called_once_with(mock_update_callback, mock_context_with_admin)

