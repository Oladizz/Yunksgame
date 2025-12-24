import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, JobQueue
import asyncio
from yunks_game_2_0_1.handlers import game_lmw
from yunks_game_2_0_1 import database

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object."""
    update = AsyncMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    update.effective_user.username = 'testuser1'
    update.effective_user.first_name = 'Test'
    update.effective_user.mention_html.return_value = "Test User 1"
    update.effective_chat.id = -12345
    
    update.message = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.message.reply_text = AsyncMock()
    
    update.callback_query = AsyncMock()
    update.callback_query.message = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.from_user = update.effective_user

    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.chat_data = {}
    context.user_data = {}
    context.bot_data = {'db': MagicMock()}
    context.args = []
    context.bot = AsyncMock()
    context.job_queue = MagicMock(spec=JobQueue)
    context.job_queue.run_once = MagicMock()
    context.job = MagicMock()
    context.job.data = {'chat_id': -12345}

    return context

@pytest.fixture
def mock_db_add_xp(mocker):
    """Fixture to mock database.add_xp."""
    return mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

@pytest.fixture
def mock_db_get_user(mocker):
    """Fixture to mock database.get_user_data."""
    mock = mocker.patch('yunks_game_2_0_1.database.get_user_data', new_callable=AsyncMock)
    mock.return_value = {'xp': 100} # Default to user having enough XP
    return mock

@pytest.mark.asyncio
async def test_start_lmw_lobby_new_lobby(mock_update, mock_context, mock_db_get_user, mock_db_add_xp):
    """Test starting a new 'Last Message Wins' lobby."""
    mock_update.callback_query = None # Set callback_query to None for this test
    mock_update.message.reply_html.return_value = MagicMock(message_id=100)

    await game_lmw.start_lmw_lobby(mock_update, mock_context)

    assert 'lmw_game' in mock_context.chat_data
    assert mock_context.chat_data['lmw_game']['status'] == 'lobby'
    assert mock_context.chat_data['lmw_game']['message_id'] == 100
    assert 1 in mock_context.chat_data['lmw_game']['players']
    assert mock_context.chat_data['lmw_game']['xp_pool'] == 10
    mock_update.message.reply_html.assert_called_once()
    assert "Last Message Wins Lobby" in mock_update.message.reply_html.call_args[0][0]
    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'testuser1', xp_to_add=-10)

@pytest.mark.asyncio
async def test_lmw_callback_handler_join_success(mock_update, mock_context, mock_db_get_user, mock_db_add_xp, mocker): # Added mocker
    """Test successfully joining a 'Last Message Wins' lobby via callback."""
    # Patch the edit_message_text method on the message mock
    mock_edit_text = mocker.patch.object(mock_update.callback_query.message, 'edit_text', new_callable=AsyncMock)

    mock_context.chat_data['lmw_game'] = {
        'status': 'lobby',
        'players': {2: {'username': 'player2', 'mention': 'Player 2'}},
        'message_id': 100,
        'job': None,
        'xp_pool': 10
    }
    mock_update.callback_query.data = 'lmw_join'
    mock_update.callback_query.from_user.id = 1
    
    await game_lmw.lmw_callback_handler(mock_update, mock_context)

    assert 1 in mock_context.chat_data['lmw_game']['players']
    assert len(mock_context.chat_data['lmw_game']['players']) == 2
    assert mock_context.chat_data['lmw_game']['xp_pool'] == 20
    mock_update.callback_query.answer.assert_called_once()
    mock_edit_text.assert_called_once()
    assert "Current players: 2" in mock_edit_text.call_args.kwargs['text']
    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'testuser1', xp_to_add=-10)

@pytest.mark.asyncio
async def test_lmw_callback_handler_start_success(mock_update, mock_context):
    """Test successfully starting a 'Last Message Wins' game."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'lobby',
        'players': {1: {}, 2: {}},
        'message_id': 100,
    }
    mock_update.callback_query.data = 'lmw_start'
    mock_update.callback_query.message.edit_text = AsyncMock()
    mock_context.bot.edit_message_text = AsyncMock()

    await game_lmw.lmw_callback_handler(mock_update, mock_context)

    assert mock_context.chat_data['lmw_game']['status'] == 'in_progress'
    mock_context.bot.edit_message_text.assert_called_once()
    assert "Last Message Wins Game Started!" in mock_context.bot.edit_message_text.call_args.kwargs['text']
    mock_context.job_queue.run_once.assert_called_once()

@pytest.mark.asyncio
async def test_handle_lmw_message(mock_update, mock_context):
    """Test handling a message during a 'Last Message Wins' game."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'players': {1: {}}
    }
    mock_update.effective_user.id = 1

    await game_lmw.handle_lmw_message(mock_update, mock_context)

    assert mock_context.chat_data['lmw_game']['last_message_user_id'] == 1

@pytest.mark.asyncio
async def test_end_lmw_game_winner(mock_update, mock_context, mock_db_add_xp):
    """Test ending a 'Last Message Wins' game with a winner."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'players': {1: {'username': 'winner', 'mention': 'Winner'}},
        'last_message_user_id': 1,
        'xp_pool': 50
    }
    
    await game_lmw.end_lmw_game(mock_context)

    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'winner', 50)
    mock_context.bot.send_message.assert_called_once()
    assert "Congratulations Winner!" in mock_context.bot.send_message.call_args.kwargs['text']
    assert 'lmw_game' not in mock_context.chat_data

@pytest.mark.asyncio
async def test_end_lmw_game_no_winner(mock_update, mock_context, mock_db_add_xp):
    """Test ending a 'Last Message Wins' game with no winner."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'players': {1: {'username': 'player1'}, 2: {'username': 'player2'}},
        'xp_pool': 20
    }

    await game_lmw.end_lmw_game(mock_context)

    assert mock_db_add_xp.call_count == 2
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], 1, 'player1', 10)
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], 2, 'player2', 10)
    mock_context.bot.send_message.assert_called_once_with(chat_id=-12345, text="No one sent a message. XP has been refunded.")
    assert 'lmw_game' not in mock_context.chat_data