import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from telegram import Update
from telegram.ext import CallbackContext

from Yunks_game.handlers import core, messages, callbacks
from Yunks_game import game
from Yunks_game import database

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.effective_user.username = 'testuser'
    update.effective_user.mention_html.return_value = 'Test User'
    update.message = AsyncMock()
    update.message.text = '/start'
    update.message.reply_html = AsyncMock()  # Added
    update.message.reply_markdown_v2 = AsyncMock() # Added
    
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.message = AsyncMock() # Added
    update.callback_query.message.chat_id = 12345 # Added mock chat_id
    update.callback_query.message.message_id = 67890 # Added mock message_id
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.user_data = {} # Initialize user_data for game state
    
    # Make context.bot and its methods awaitable for strict_edit_message
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.username = "MockBotUsername" # Added to fix TypeError
    return context

@pytest.mark.asyncio
async def test_start_command_from_callback(mock_update, mock_context, mocker):
    """Test the start command when triggered by a callback query."""
    # This is the default behavior of the mock_update fixture
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.core.strict_edit_message', new_callable=AsyncMock)
    await core.start(mock_update, mock_context)
    mock_strict_edit_message.assert_called_once()

@pytest.mark.asyncio
async def test_start_command_from_message(mock_update, mock_context):
    """Test the start command when triggered by a /start message."""
    mock_update.callback_query = None # Ensure it's treated as a message
    await core.start(mock_update, mock_context)
    mock_update.message.reply_html.assert_called_once()

@pytest.mark.asyncio
async def test_help_command_message(mock_update, mock_context):
    """Test the help command via message."""
    mock_update.callback_query = None
    await core.help_command(mock_update, mock_context)
    mock_update.message.reply_html.assert_called_once()

@pytest.mark.asyncio
async def test_help_command_callback(mock_context, mocker): # Removed mock_update from args
    """Test the help command via callback query."""
    # Explicitly create an update object for this test
    mock_update = AsyncMock(spec=Update)
    mock_update.effective_user.id = 123 # Example user ID
    mock_update.effective_user.username = 'testuser'
    mock_update.message = None # Crucially, message is None for callback query
    
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.from_user.id = 123
    mock_update.callback_query.message = AsyncMock()
    mock_update.callback_query.message.chat_id = 12345
    mock_update.callback_query.message.message_id = 67890

    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.core.strict_edit_message', new_callable=AsyncMock)
    await core.help_command(mock_update, mock_context)
    mock_strict_edit_message.assert_called_once_with(ANY, ANY, ANY, ANY, None, parse_mode='HTML')

@pytest.mark.asyncio
async def test_handle_message_xp_added(mock_update, mock_context, mocker):
    """Test handling a regular message which adds XP."""
    mock_update.message.text = 'Hello there!'
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp')
    await messages.handle_message(mock_update, mock_context)
    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], mock_update.effective_user.id, mock_update.effective_user.username)

@pytest.mark.asyncio
async def test_handle_message_command_ignored(mock_update, mock_context, mocker):
    """Test handling a command message (should be ignored by handle_message)."""
    mock_update.message.text = '/somecommand'
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp')
    await messages.handle_message(mock_update, mock_context)
    mock_add_xp.assert_not_called()

@pytest.mark.asyncio
async def test_handle_message_game_guess(mock_update, mock_context, mocker):
    """Test handling a message as a game guess."""
    mock_update.message.text = '50'
    mock_context.user_data['game'] = {'secret_number': 50, 'tries_left': 5}
    mock_handle_guess = mocker.patch('Yunks_game.game.handle_guess', new_callable=AsyncMock)
    await messages.handle_message(mock_update, mock_context)
    mock_handle_guess.assert_called_once_with(mock_update, mock_context)

@pytest.mark.asyncio
async def test_unknown_command(mock_update, mock_context):
    """Test handling an unknown command."""
    mock_update.message.text = '/unknown'
    await messages.unknown_command(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("Sorry, I didn't understand that command.")

@pytest.mark.asyncio
async def test_button_handler_profile_exists(mock_update, mock_context, mocker):
    """Test button handler for profile when user data exists."""
    mock_update.callback_query.data = 'profile'
    mock_get_user_data = mocker.patch('Yunks_game.database.get_user_data', return_value={'username': 'testuser', 'xp': 100})
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_get_user_data.assert_called_once_with(mock_context.bot_data['db'], mock_update.callback_query.from_user.id)
    mock_strict_edit_message.assert_called_once()

@pytest.mark.asyncio
async def test_button_handler_profile_not_exists(mock_update, mock_context, mocker):
    """Test button handler for profile when user data does not exist."""
    mock_update.callback_query.data = 'profile'
    mock_get_user_data = mocker.patch('Yunks_game.database.get_user_data', return_value=None)
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_get_user_data.assert_called_once_with(mock_context.bot_data['db'], mock_update.callback_query.from_user.id)
    mock_strict_edit_message.assert_called_once_with(mock_context, mock_update.callback_query.message.chat_id, mock_update.callback_query.message.message_id, "You don't have a profile yet. Send some messages to start!", None, parse_mode='HTML')

@pytest.mark.asyncio
async def test_button_handler_leaderboard_empty(mock_update, mock_context, mocker):
    """Test button handler for leaderboard when it's empty."""
    mock_update.callback_query.data = 'leaderboard'
    mock_get_leaderboard = mocker.patch('Yunks_game.database.get_leaderboard', return_value=[])
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_get_leaderboard.assert_called_once_with(mock_context.bot_data['db'])
    mock_strict_edit_message.assert_called_once_with(mock_context, mock_update.callback_query.message.chat_id, mock_update.callback_query.message.message_id, "The leaderboard is currently empty. Start sending messages to get on it!", None, parse_mode='HTML')

@pytest.mark.asyncio
async def test_button_handler_leaderboard_populated(mock_update, mock_context, mocker):
    """Test button handler for leaderboard when it's populated."""
    mock_update.callback_query.data = 'leaderboard'
    mock_get_leaderboard = mocker.patch('Yunks_game.database.get_leaderboard', return_value=[('user2', 200), ('user1', 100)])
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_get_leaderboard.assert_called_once_with(mock_context.bot_data['db'])
    mock_strict_edit_message.assert_called_once()
    assert "🏆 <b>Top 10 Players</b>" in mock_strict_edit_message.call_args[0][3] # Check 'new_text' argument

@pytest.mark.asyncio
async def test_button_handler_game_menu(mock_update, mock_context, mocker):
    """Test button handler for game menu."""
    mock_update.callback_query.data = 'game_menu'
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_strict_edit_message.assert_called_once()

@pytest.mark.asyncio
async def test_button_handler_help_menu(mock_update, mock_context, mocker):
    """Test button handler for help menu."""
    mock_update.callback_query.data = 'help_menu'
    mock_help_command = mocker.patch('Yunks_game.handlers.core.help_command', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_help_command.assert_called_once_with(mock_update, mock_context)

@pytest.mark.asyncio
async def test_button_handler_unknown_action(mock_update, mock_context, mocker):
    """Test button handler for an unknown action."""
    mock_update.callback_query.data = 'unknown_action'
    mock_strict_edit_message = mocker.patch('Yunks_game.handlers.callbacks.strict_edit_message', new_callable=AsyncMock)
    await callbacks.button_handler(mock_update, mock_context)
    mock_update.callback_query.answer.assert_called_once()
    mock_strict_edit_message.assert_called_once_with(mock_context, mock_update.callback_query.message.chat_id, mock_update.callback_query.message.message_id, "Unknown action.", None, parse_mode='HTML')

@pytest.mark.asyncio
async def test_start_game_command(mock_update, mock_context, mocker):
    """Test the /start_game command."""
    mock_start_new_game = mocker.patch('Yunks_game.game.start_new_game', new_callable=AsyncMock)
    mock_update.message.text = '/start_game' # Simulate a command message
    await game.start_new_game(mock_update, mock_context)
    mock_start_new_game.assert_called_once_with(mock_update, mock_context)