import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update
from telegram.ext import CallbackContext, JobQueue
import asyncio
import time

from yunks_game_2_0_1.handlers import last_message_wins_game
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
    update.callback_query.edit_text = AsyncMock()
    update.callback_query.message = AsyncMock()
    update.callback_query.message.chat_id = -12345
    update.callback_query.message.reply_markup = MagicMock()
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
    context.job.data = {'chat_id': -12345, 'countdown_message_id': 200}
    return context

@pytest.fixture
def mock_db_add_xp(mocker):
    """Fixture to mock database.add_xp."""
    return mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

@pytest.fixture
def mock_db_get_user(mocker):
    """Fixture to mock database.get_user_data."""
    return mocker.patch('yunks_game_2_0_1.database.get_user_data', new_callable=AsyncMock)

@pytest.mark.asyncio
async def test_start_lmw_lobby_new_lobby_success(mock_update, mock_context, mock_db_get_user, mock_db_add_xp):
    """Test starting a new 'Last Message Wins' lobby successfully."""
    mock_db_get_user.return_value = {'xp': 100}
    mock_update.message.reply_html.return_value = MagicMock(message_id=100)

    await last_message_wins_game.start_lmw_lobby(mock_update, mock_context)

    assert 'lmw_game' in mock_context.chat_data
    assert mock_context.chat_data['lmw_game']['status'] == 'lobby'
    assert 1 in mock_context.chat_data['lmw_game']['players']
    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'testuser1', -last_message_wins_game.LMW_ENTRY_COST)
    assert mock_context.chat_data['lmw_game']['xp_pot'] > 0
    mock_update.message.reply_html.assert_called_once()
    assert "Last Message Wins Lobby" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_start_lmw_lobby_insufficient_xp(mock_update, mock_context, mock_db_get_user):
    """Test starting a lobby with insufficient XP."""
    mock_db_get_user.return_value = {'xp': 2} # Less than LMW_ENTRY_COST
    
    await last_message_wins_game.start_lmw_lobby(mock_update, mock_context)

    assert 'lmw_game' not in mock_context.chat_data
    mock_update.message.reply_text.assert_called_once_with(f"You need at least {last_message_wins_game.LMW_ENTRY_COST} XP to join this game!")

@pytest.mark.asyncio
async def test_lmw_callback_handler_join_success(mock_update, mock_context, mock_db_get_user, mock_db_add_xp):
    """Test successfully joining a lobby via callback."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'lobby', 'players': {2: {'username': 'p2', 'mention': 'P2'}}, 'message_id': 100, 'xp_pot': 2
    }
    mock_update.callback_query.data = 'lmw_join'
    mock_update.callback_query.from_user.id = 1
    mock_db_get_user.return_value = {'xp': 50}

    await last_message_wins_game.lmw_callback_handler(mock_update, mock_context)

    mock_update.callback_query.answer.assert_called_once()
    assert 1 in mock_context.chat_data['lmw_game']['players']
    assert len(mock_context.chat_data['lmw_game']['players']) == 2
    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'testuser1', -last_message_wins_game.LMW_ENTRY_COST)
    mock_context.bot.edit_message_text.assert_called_once()

@pytest.mark.asyncio
async def test_lmw_callback_handler_start_success(mock_update, mock_context, mocker):
    """Test successfully starting the game."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'lobby',
        'players': {1: {'mention': 'P1'}, 2: {'mention': 'P2'}},
        'message_id': 100,
        'xp_pot': 5,
        'job': None
    }
    mock_update.callback_query.data = 'lmw_start'
    mock_start_game = mocker.patch('yunks_game_2_0_1.handlers.last_message_wins_game.start_lmw_game', new_callable=AsyncMock)

    await last_message_wins_game.lmw_callback_handler(mock_update, mock_context)

    assert mock_context.chat_data['lmw_game']['status'] == 'in_progress'
    mock_context.bot.edit_message_text.assert_called_once()
    assert "Game Started!" in mock_context.bot.edit_message_text.call_args[1]['text']
    mock_start_game.assert_called_once()

@pytest.mark.asyncio
async def test_lmw_message_handler_records_message(mock_update, mock_context):
    """Test that the message handler correctly records a player's message."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'players': {1: {'has_messaged': False}},
        'last_message_info': {'user_id': None}
    }
    mock_update.effective_user.id = 1
    mock_update.message.message_id = 555

    await last_message_wins_game.lmw_message_handler(mock_update, mock_context)

    assert mock_context.chat_data['lmw_game']['last_message_info']['user_id'] == 1
    assert mock_context.chat_data['lmw_game']['last_message_info']['message_id'] == 555
    assert mock_context.chat_data['lmw_game']['players'][1]['has_messaged'] is True

@pytest.mark.asyncio
async def test_lmw_message_handler_already_messaged(mock_update, mock_context):
    """Test that a player cannot send more than one message."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'players': {1: {'has_messaged': True}},
    }
    mock_update.effective_user.id = 1

    await last_message_wins_game.lmw_message_handler(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("You have already sent your message for this round!")

@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock) # Prevent sleeping in tests
async def test_start_lmw_game_schedules_end(mock_sleep, mock_update, mock_context):
    """Test that starting the game schedules the end_lmw_game job."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress', 'players': {}, 'job': None
    }
    mock_context.bot.send_message.return_value = MagicMock(message_id=200)

    await last_message_wins_game.start_lmw_game(mock_update, mock_context)

    mock_context.job_queue.run_once.assert_called_once_with(
        last_message_wins_game.end_lmw_game,
        last_message_wins_game.LMW_GAME_DURATION,
        data={'chat_id': -12345, 'countdown_message_id': 200},
        chat_id=-12345,
        name='lmw_end_game_-12345'
    )
    assert mock_context.bot.send_message.called

@pytest.mark.asyncio
async def test_end_lmw_game_with_winner(mock_context, mock_db_add_xp):
    """Test ending the game with a winner."""
    winner_id = 1
    winner_username = 'winner'
    xp_pot = 50
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'last_message_info': {'user_id': winner_id, 'username': winner_username, 'message_id': 999},
        'xp_pot': xp_pot
    }
    
    # Mock get_chat_member to return a mock user object
    mock_chat_member = MagicMock()
    mock_chat_member.user.mention_html.return_value = "Winner Mention"
    mock_context.bot.get_chat_member.return_value = mock_chat_member

    await last_message_wins_game.end_lmw_game(mock_context)

    mock_db_add_xp.assert_called_once_with(mock_context.bot_data['db'], winner_id, winner_username, xp_pot)
    mock_context.bot.send_message.assert_called_once()
    assert "The winner is Winner Mention" in mock_context.bot.send_message.call_args.kwargs['text']
    assert 'lmw_game' not in mock_context.chat_data # Check cleanup

@pytest.mark.asyncio
async def test_end_lmw_game_no_winner(mock_context, mock_db_add_xp):
    """Test ending the game with no winner."""
    mock_context.chat_data['lmw_game'] = {
        'status': 'in_progress',
        'last_message_info': {'user_id': None},
        'xp_pot': 50
    }
    mock_context.job.data = {'chat_id': -12345, 'countdown_message_id': 200}


    await last_message_wins_game.end_lmw_game(mock_context)

    mock_db_add_xp.assert_not_called()
    mock_context.bot.edit_message_text.assert_called_once()
    assert "No one sent a message" in mock_context.bot.edit_message_text.call_args.kwargs['text']
    assert 'lmw_game' not in mock_context.chat_data
