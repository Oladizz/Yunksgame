import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, JobQueue
import asyncio
from yunks_game_2_0_1.handlers import lastman_game
from yunks_game_2_0_1 import database

@pytest.fixture
def mock_update_message():
    """Fixture for a mock Update object for command/message handlers."""
    update = AsyncMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    update.effective_user.username = 'testuser1'
    update.effective_user.first_name = 'Test'
    update.effective_user.mention_html.return_value = "Test User 1"
    update.effective_chat.id = -12345
    
    update.message = AsyncMock()
    # Corrected: reply_html should return a mock message object when awaited
    update.message.reply_html = AsyncMock(return_value=MagicMock(message_id=100))
    update.message.reply_text = AsyncMock()
    
    update.callback_query = None # Explicitly set to None for message-based updates

    return update

@pytest.fixture
def mock_update_callback_query():
    """Fixture for a mock Update object for callback query handlers."""
    update = AsyncMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    update.effective_user.username = 'testuser1'
    update.effective_user.first_name = 'Test'
    update.effective_user.mention_html.return_value = "Test User 1"
    update.effective_chat.id = -12345
    
    update.message = None # Explicitly set to None for callback-based updates
    
    update.callback_query = AsyncMock()
    update.callback_query.message = AsyncMock()
    update.callback_query.message.edit_text = AsyncMock() # Mock edit_text on the message object within the callback
    update.callback_query.answer = AsyncMock()
    update.callback_query.from_user = update.effective_user # For callbacks

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
    context.job = MagicMock() # For perform_elimination to access context.job.data
    context.job.data = {'chat_id': -12345} # Default chat_id for job data
    return context

@pytest.fixture
def mock_db_add_xp(mocker):
    """Fixture to mock database.add_xp."""
    return mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

@pytest.mark.asyncio
async def test_start_lastman_lobby_new_lobby(mock_update_message, mock_context):
    """Test starting a new 'Last Person Standing' lobby."""
    await lastman_game.start_lastman_lobby(mock_update_message, mock_context)

    assert 'lastman_game' in mock_context.chat_data
    assert mock_context.chat_data['lastman_game']['status'] == 'lobby'
    assert mock_context.chat_data['lastman_game']['message_id'] == 100
    assert 1 in mock_context.chat_data['lastman_game']['players']
    mock_update_message.message.reply_html.assert_called_once()
    assert "Last Person Standing Lobby" in mock_update_message.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_start_lastman_lobby_join_existing(mock_update_message, mock_context):
    """Test joining an existing lobby."""
    # Pre-populate chat_data with an existing lobby
    mock_context.chat_data['lastman_game'] = {
        'status': 'lobby',
        'players': {2: {'username': 'player2', 'mention': 'Player 2'}},
        'message_id': 100,
        'job': None
    }
    # Mock for a different user joining
    mock_update_message.effective_user.id = 1
    mock_update_message.effective_user.username = 'testuser1'
    mock_update_message.effective_user.first_name = 'Test'
    mock_update_message.effective_user.mention_html.return_value = "Test User 1"
    
    await lastman_game.start_lastman_lobby(mock_update_message, mock_context)

    assert 1 in mock_context.chat_data['lastman_game']['players']
    assert len(mock_context.chat_data['lastman_game']['players']) == 2
    mock_update_message.message.reply_html.assert_not_called() # Should edit existing message
    mock_context.bot.edit_message_text.assert_called_once()
    assert "Current players: 2" in mock_context.bot.edit_message_text.call_args[1]['text']

@pytest.mark.asyncio
async def test_start_lastman_lobby_already_in_game(mock_update_message, mock_context):
    """Test trying to start/join a lobby when already in it."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'lobby',
        'players': {1: {'username': 'testuser1', 'mention': 'Test User 1'}},
        'message_id': 100,
        'job': None
    }
    mock_update_message.effective_user.id = 1 # Same user
    
    await lastman_game.start_lastman_lobby(mock_update_message, mock_context)
    mock_update_message.message.reply_text.assert_called_once_with("You are already in the lobby!")
    assert len(mock_context.chat_data['lastman_game']['players']) == 1 # No new player added

@pytest.mark.asyncio
async def test_lastman_callback_handler_join_success(mock_update_callback_query, mock_context, mocker):
    """Test successfully joining via callback."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'lobby',
        'players': {2: {'username': 'player2', 'mention': 'Player 2'}},
        'message_id': 100,
        'job': None
    }
    mock_update_callback_query.callback_query.data = 'lastman_join'
    mock_update_callback_query.callback_query.from_user.id = 1
    mock_update_callback_query.callback_query.from_user.username = 'testuser1'
    mock_update_callback_query.callback_query.from_user.first_name = 'Test'
    mock_update_callback_query.callback_query.from_user.mention_html.return_value = "Test User 1"

    await lastman_game.lastman_callback_handler(mock_update_callback_query, mock_context)

    mock_update_callback_query.callback_query.answer.assert_called_once()
    mock_update_callback_query.callback_query.message.edit_text.assert_called_once()
    assert "Current players: 2" in mock_update_callback_query.callback_query.message.edit_text.call_args.kwargs['text']
    assert 1 in mock_context.chat_data['lastman_game']['players']
    assert len(mock_context.chat_data['lastman_game']['players']) == 2

@pytest.mark.asyncio
async def test_lastman_callback_handler_join_game_started(mock_update_callback_query, mock_context):
    """Test trying to join via callback when game has started."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'in_progress',
        'players': {1: {'username': 'player1', 'mention': 'Player 1'}},
        'message_id': 100,
        'job': None
    }
    mock_update_callback_query.callback_query.data = 'lastman_join'
    mock_update_callback_query.callback_query.from_user.id = 2 # New user trying to join

    await lastman_game.lastman_callback_handler(mock_update_callback_query, mock_context)
    # query.answer() is called once initially, then again for the alert
    assert mock_update_callback_query.callback_query.answer.call_count == 2
    mock_update_callback_query.callback_query.message.edit_text.assert_not_called()
    assert mock_update_callback_query.callback_query.answer.call_args_list[1].args[0] == "Game already started!"
    assert mock_update_callback_query.callback_query.answer.call_args_list[1].kwargs['show_alert'] is True
    assert 2 not in mock_context.chat_data['lastman_game']['players']

@pytest.mark.asyncio
async def test_lastman_callback_handler_start_insufficient_players(mock_update_callback_query, mock_context):
    """Test trying to start the game with insufficient players."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'lobby',
        'players': {1: {'username': 'player1', 'mention': 'Player 1'}}, # Only one player
        'message_id': 100,
        'job': None
    }
    mock_update_callback_query.callback_query.data = 'lastman_start'

    await lastman_game.lastman_callback_handler(mock_update_callback_query, mock_context)
    # query.answer() is called once initially, then again for the alert
    assert mock_update_callback_query.callback_query.answer.call_count == 2
    mock_update_callback_query.callback_query.message.edit_text.assert_not_called()
    assert mock_update_callback_query.callback_query.answer.call_args_list[1].args[0] == "Need at least 2 players to start the game!"
    assert mock_update_callback_query.callback_query.answer.call_args_list[1].kwargs['show_alert'] is True
    assert mock_context.chat_data['lastman_game']['status'] == 'lobby' # Still in lobby

@pytest.mark.asyncio
async def test_lastman_callback_handler_start_success(mock_update_callback_query, mock_context, mocker):
    """Test successfully starting the game with enough players."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'lobby',
        'players': {
            1: {'username': 'player1', 'mention': 'Player 1'},
            2: {'username': 'player2', 'mention': 'Player 2'},
            3: {'username': 'player3', 'mention': 'Player 3'},
            4: {'username': 'player4', 'mention': 'Player 4'}
        },
        'message_id': 100,
        'job': None
    }
    mock_update_callback_query.callback_query.data = 'lastman_start'
    
    # Patch start_elimination_phase to prevent actual job scheduling during unit test
    mocker.patch('yunks_game_2_0_1.handlers.lastman_game.start_elimination_phase', new_callable=AsyncMock)

    await lastman_game.lastman_callback_handler(mock_update_callback_query, mock_context)

    mock_update_callback_query.callback_query.answer.assert_called_once()
    mock_context.bot.edit_message_text.assert_called_once()
    assert "Game Started!" in mock_context.bot.edit_message_text.call_args.kwargs['text']
    assert mock_context.chat_data['lastman_game']['status'] == 'in_progress'
    lastman_game.start_elimination_phase.assert_called_once()

@pytest.mark.asyncio
@patch('random.shuffle')
@patch('yunks_game_2_0_1.handlers.lastman_game.notify_next_elimination', new_callable=AsyncMock)
async def test_start_elimination_phase(mock_notify, mock_shuffle, mock_update_callback_query, mock_context):
    """Test the initiation of the elimination phase."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'in_progress',
        'players': {
            1: {'username': 'player1', 'mention': 'Player 1'},
            2: {'username': 'player2', 'mention': 'Player 2'},
            3: {'username': 'player3', 'mention': 'Player 3'},
            4: {'username': 'player4', 'mention': 'Player 4'}
        },
        'message_id': 100,
        'job': None
    }
    await lastman_game.start_elimination_phase(mock_update_callback_query, mock_context)

    assert mock_shuffle.called
    assert len(mock_context.chat_data['lastman_game']['players_remaining']) == 4
    assert mock_context.chat_data['lastman_game']['round'] == 0
    mock_notify.assert_called_once_with(mock_context, mock_update_callback_query.effective_chat.id)

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.lastman_game.ELIMINATION_INTERVAL', 0.1) # Shorter interval for testing
@patch('yunks_game_2_0_1.handlers.lastman_game.end_lastman_game', new_callable=AsyncMock)
@patch('yunks_game_2_0_1.handlers.lastman_game.notify_next_elimination', new_callable=AsyncMock)
async def test_perform_elimination(mock_notify_next_elimination, mock_end_game, mock_update_callback_query, mock_context):
    """Test a single elimination."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'in_progress',
        'players': {
            1: {'username': 'player1', 'mention': 'Test User 1'},
            2: {'username': 'player2', 'mention': 'Player 2'},
            3: {'username': 'player3', 'mention': 'Player 3'},
            4: {'username': 'player4', 'mention': 'Player 4'}
        },
        'message_id': 100,
        'job': None,
        'players_remaining': [1, 2, 3, 4], # Ordered for predictable pop
        'eliminated_players': [],
        'round': 1
    }
    mock_context.bot.send_message.return_value = MagicMock(message_id=200) # For elimination message

    await lastman_game.perform_elimination(mock_context)

    mock_context.bot.send_message.assert_called_once()
    assert "💀 Test User 1 has been eliminated!" in mock_context.bot.send_message.call_args.kwargs['text']
    assert len(mock_context.chat_data['lastman_game']['players_remaining']) == 3
    assert len(mock_context.chat_data['lastman_game']['eliminated_players']) == 1
    mock_notify_next_elimination.assert_not_called()
    mock_end_game.assert_called_once() # Not enough eliminations yet

@pytest.mark.asyncio
@patch('yunks_game_2_0_1.handlers.lastman_game.XP_AWARD_TOP_3', 5)
async def test_end_lastman_game(mock_db_add_xp, mock_update_callback_query, mock_context):
    """Test ending the game and awarding XP."""
    mock_context.chat_data['lastman_game'] = {
        'status': 'in_progress',
        'players': {
            1: {'username': 'winner1', 'mention': 'Test User 1'},
            2: {'username': 'winner2', 'mention': 'Test User 1'},
            3: {'username': 'winner3', 'mention': 'Test User 1'}
        },
        'message_id': 100,
        'job': None,
        'players_remaining': [1, 2, 3],
        'eliminated_players': [],
        'round': 1
    }

    await lastman_game.end_lastman_game(mock_context, mock_update_callback_query.effective_chat.id)

    mock_context.bot.send_message.assert_called_once()
    assert "🏆 <b>Game Over! The last players standing are:</b> Test User 1, Test User 1, Test User 1!" in mock_context.bot.send_message.call_args.kwargs['text']
    assert "They each earned 5 XP!" in mock_context.bot.send_message.call_args.kwargs['text']
    assert 'lastman_game' not in mock_context.chat_data # Game data should be cleared
    assert mock_db_add_xp.call_count == 3
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], 1, 'winner1', 5)
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], 2, 'winner2', 5)
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], 3, 'winner3', 5)