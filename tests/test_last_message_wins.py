import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, JobQueue
import time

from Yunks_game.game_logic.last_message_wins import LastMessageWinsGame, LastMessageWinsStatus
from Yunks_game.handlers import last_message_wins_handler
from Yunks_game import database as db
from Yunks_game.game_logic.player import Player # To get player data for XP handling

# --- Fixtures ---

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.effective_user.username = 'testuser'
    update.effective_user.mention_html.return_value = 'Test User'
    update.message = AsyncMock()
    update.message.chat_id = 12345 # Explicitly set chat_id
    update.message.message_id = 67890 # Explicitly set message_id
    update.message.reply_text = AsyncMock()
    update.message.delete = AsyncMock() # For deleting invalid messages
    
    # Mock effective_chat for command calls
    update.effective_chat.id = 12345
    
    # Mock callback_query for button interactions
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.from_user.username = 'testuser'
    update.callback_query.message = AsyncMock()
    update.callback_query.message.chat_id = 12345
    update.callback_query.message.message_id = 67890
    update.callback_query.answer = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    
    mock_db = MagicMock(spec=db)
    mock_db.get_user_data = AsyncMock(return_value={'xp': 100}) # Default enough XP
    mock_db.add_xp = AsyncMock() # For XP deductions/awards/refunds
    context.bot_data = {'db': mock_db}
    context.chat_data = {}
    context.user_data = {}
    
    # Mock job_queue
    context.job_queue = MagicMock(spec=JobQueue)
    context.job_queue.run_once = MagicMock()
    context.job_queue.run_repeating = MagicMock()

    # Mock bot for strict_edit_message and send_message
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.pin_chat_message = AsyncMock()
    context.bot.unpin_chat_message = AsyncMock()
    return context

@pytest.fixture
def lmw_game_instance():
    """Fixture for a LastMessageWinsGame instance."""
    return LastMessageWinsGame(chat_id=12345, owner_id=123, initial_countdown=10, entry_xp_cost=2)

# --- Test LastMessageWinsGame Class ---

def test_lmw_init(lmw_game_instance):
    assert lmw_game_instance.chat_id == 12345
    assert lmw_game_instance.owner_id == 123
    assert lmw_game_instance.status == LastMessageWinsStatus.LOBBY
    assert lmw_game_instance.xp_pool == 0
    assert lmw_game_instance.countdown_total == 10
    assert lmw_game_instance.entry_xp_cost == 2

def test_lmw_add_player(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    assert len(lmw_game_instance.players) == 1
    assert lmw_game_instance.players[1] == "player1"
    assert lmw_game_instance.xp_pool == 2
    assert lmw_game_instance.has_sent_message[1] is False

def test_lmw_remove_player(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.remove_player(1)
    assert len(lmw_game_instance.players) == 0
    assert lmw_game_instance.xp_pool == 0

def test_lmw_start_countdown_success(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    assert lmw_game_instance.start_countdown() is True
    assert lmw_game_instance.status == LastMessageWinsStatus.COUNTDOWN
    assert lmw_game_instance.countdown_end_time is not None

def test_lmw_start_countdown_fail_no_players(lmw_game_instance):
    assert lmw_game_instance.start_countdown() is False
    assert lmw_game_instance.status == LastMessageWinsStatus.LOBBY

@patch('time.time', MagicMock(return_value=100.0))
def test_lmw_record_message_success(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    result = lmw_game_instance.record_message(1, "player1", 1001)
    assert result is True
    assert lmw_game_instance.last_valid_message['user_id'] == 1
    assert lmw_game_instance.last_valid_message['message_id'] == 1001
    assert lmw_game_instance.has_sent_message[1] is True

@patch('time.time', MagicMock(return_value=100.0))
def test_lmw_record_message_fail_already_sent(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    lmw_game_instance.record_message(1, "player1", 1001)
    result = lmw_game_instance.record_message(1, "player1", 1002) # Second message
    assert result is False
    assert lmw_game_instance.last_valid_message['message_id'] == 1001 # Should not update

@patch('time.time', MagicMock(return_value=100.0))
def test_lmw_is_countdown_over_true(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    time.time.return_value = 100.0 + lmw_game_instance.countdown_total + 1 # After end time
    assert lmw_game_instance.is_countdown_over() is True

@patch('time.time', MagicMock(return_value=100.0))
def test_lmw_determine_winner(lmw_game_instance):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    lmw_game_instance.record_message(1, "player1", 1001)
    time.time.return_value = 100.0 + lmw_game_instance.countdown_total + 1 # After end time
    winner = lmw_game_instance.determine_winner()
    assert winner['user_id'] == 1
    assert lmw_game_instance.status == LastMessageWinsStatus.FINISHED

# --- Test Handlers ---

@pytest.mark.asyncio
async def test_start_lmw_game_command(mock_update, mock_context, mocker):
    mock_update.callback_query = None # Simulate command
    mocker.patch('Yunks_game.handlers.last_message_wins_handler.render_lmw_game', return_value=("text", InlineKeyboardMarkup([])))
    
    await last_message_wins_handler.start_lmw_game(mock_update, mock_context)
    
    assert 'last_message_wins_game' in mock_context.chat_data
    game = mock_context.chat_data['last_message_wins_game']
    assert game.owner_id == mock_update.effective_user.id
    mock_context.bot.send_message.assert_called_once()
    mock_context.job_queue.run_once.assert_called_once_with(
        last_message_wins_handler.lmw_lobby_timeout, 
        last_message_wins_handler.LMW_GAME_TIMEOUT_SECONDS,
        context={'chat_id': 12345, 'game_message_id': game.game_message_id},
        name=f"lmw_lobby_timeout_{12345}"
    )

@pytest.mark.asyncio
async def test_lmw_lobby_timeout(mock_context, lmw_game_instance):
    chat_id = lmw_game_instance.chat_id
    game_message_id = 123456 # Dummy message ID
    lmw_game_instance.game_message_id = game_message_id
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    mock_context.job = MagicMock()
    mock_context.job.context = {'chat_id': chat_id, 'game_message_id': game_message_id}

    await last_message_wins_handler.lmw_lobby_timeout(mock_context)
    
    mock_context.bot.edit_message_text.assert_called_once()
    assert 'last_message_wins_game' not in mock_context.chat_data

@pytest.mark.asyncio
async def test_handle_lmw_callback_join_success(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.callback_query.data = 'lmw_join'
    mock_update.callback_query.from_user.id = 456
    mock_update.callback_query.from_user.username = 'player2'
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    
    # Mocking lmw_lobby_timeout job for removal test
    mock_job = MagicMock()
    mock_job.schedule_removal = MagicMock()
    mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

    mocker.patch('Yunks_game.handlers.last_message_wins_handler.strict_edit_message', new_callable=AsyncMock)
    
    # Patch the actual database functions imported by the handler
    mock_get_user_data = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.get_user_data', new_callable=AsyncMock, return_value={'xp': 100})
    mock_add_xp = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.add_xp', new_callable=AsyncMock)

    await last_message_wins_handler.handle_lmw_callback(mock_update, mock_context)
    
    mock_get_user_data.assert_called_once_with(mock_context.bot_data['db'], 456)
    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 456, 'player2', xp_to_add=-lmw_game_instance.entry_xp_cost)
    assert len(lmw_game_instance.players) == 1 # Owner is not automatically added to LMW game
    assert lmw_game_instance.players[456] == 'player2'
    assert lmw_game_instance.xp_pool == lmw_game_instance.entry_xp_cost
    mock_job.schedule_removal.assert_called_once()


@pytest.mark.asyncio
async def test_handle_lmw_callback_join_insufficient_xp(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.callback_query.data = 'lmw_join'
    mock_update.callback_query.from_user.id = 456
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    
    # Patch the actual database functions imported by the handler
    mock_get_user_data = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.get_user_data', new_callable=AsyncMock, return_value={'xp': 1}) # Not enough XP
    mock_add_xp = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.add_xp', new_callable=AsyncMock)

    await last_message_wins_handler.handle_lmw_callback(mock_update, mock_context)
    
    mock_get_user_data.assert_called_once_with(mock_context.bot_data['db'], 456)
    mock_add_xp.assert_not_called()
    assert len(lmw_game_instance.players) == 0 # No player added
    mock_update.callback_query.answer.assert_called_with(f"You need at least {lmw_game_instance.entry_xp_cost} XP to join!", show_alert=True)

@pytest.mark.asyncio
async def test_handle_lmw_callback_leave_success(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.callback_query.data = 'lmw_leave'
    mock_update.callback_query.from_user.id = 456
    mock_update.callback_query.from_user.username = 'player2'
    lmw_game_instance.add_player(456, "player2") # Add player first
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance

    mocker.patch('Yunks_game.handlers.last_message_wins_handler.strict_edit_message', new_callable=AsyncMock)
    
    # Patch the actual database functions imported by the handler
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)

    await last_message_wins_handler.handle_lmw_callback(mock_update, mock_context)
    
    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 456, 'player2', xp_to_add=lmw_game_instance.entry_xp_cost)
    assert len(lmw_game_instance.players) == 0 # Player removed
    assert lmw_game_instance.xp_pool == 0 # XP refunded

@pytest.mark.asyncio
async def test_handle_lmw_callback_start_game_success(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.callback_query.data = 'lmw_start_game'
    mock_update.callback_query.from_user.id = lmw_game_instance.owner_id # Owner starts
    lmw_game_instance.add_player(101, "player1") # Add a player
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance

    # Mocking lmw_lobby_timeout job for removal test
    mock_job = MagicMock()
    mock_job.schedule_removal = MagicMock()
    mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

    mocker.patch('Yunks_game.handlers.last_message_wins_handler.strict_edit_message', new_callable=AsyncMock)

    await last_message_wins_handler.handle_lmw_callback(mock_update, mock_context)
    
    mock_job.schedule_removal.assert_called_once()
    assert lmw_game_instance.status == LastMessageWinsStatus.COUNTDOWN
    mock_context.bot.send_message.assert_called_once() # Announce game start
    mock_context.job_queue.run_repeating.assert_called_once_with(
        last_message_wins_handler.check_lmw_countdown,
        interval=1,
        first=1,
        context={'chat_id': lmw_game_instance.chat_id, 'game_message_id': lmw_game_instance.game_message_id},
        name=last_message_wins_handler.LMW_COUNTDOWN_JOB_NAME
    )

@pytest.mark.asyncio
@patch('time.time', MagicMock(return_value=100.0)) # Consistent time for message recording
async def test_handle_lmw_message_valid_first_message(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.message.text = "Hello"
    lmw_game_instance.add_player(mock_update.effective_user.id, mock_update.effective_user.username)
    lmw_game_instance.start_countdown()
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance

    await last_message_wins_handler.handle_lmw_message(mock_update, mock_context)
    
    assert lmw_game_instance.last_valid_message['user_id'] == mock_update.effective_user.id
    assert lmw_game_instance.has_sent_message[mock_update.effective_user.id] is True
    mock_context.bot.send_message.assert_called_once() # For "recorded valid message"
    mock_update.message.delete.assert_not_called()

@pytest.mark.asyncio
@patch('time.time', MagicMock(return_value=100.0)) # Consistent time for message recording
async def test_handle_lmw_message_invalid_second_message(mock_update, mock_context, lmw_game_instance, mocker):
    mock_update.message.text = "Hello again"
    lmw_game_instance.add_player(mock_update.effective_user.id, mock_update.effective_user.username)
    lmw_game_instance.start_countdown()
    lmw_game_instance.record_message(mock_update.effective_user.id, mock_update.effective_user.username, 100) # Send first message
    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance

    await last_message_wins_handler.handle_lmw_message(mock_update, mock_context)
    
    mock_update.message.delete.assert_called_once()
    mock_context.bot.send_message.assert_called_once() # For "you can only send ONE message!"
    assert lmw_game_instance.last_valid_message['message_id'] == 100 # Should not update

@pytest.mark.asyncio
async def test_check_lmw_countdown_winner(mock_context, lmw_game_instance, mocker):
    mocker.patch('time.time', return_value=100.0) # Initial time for setup

    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    lmw_game_instance.record_message(1, "player1", 1001)
    lmw_game_instance.xp_pool = 10 # Set some XP

    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    mock_context.job = MagicMock()
    mock_context.job.context = {'chat_id': lmw_game_instance.chat_id, 'game_message_id': lmw_game_instance.game_message_id}
    mock_context.job.schedule_removal = MagicMock() # Mock job removal

    # Advance time to after countdown ends
    mocker.patch('time.time', return_value=100.0 + lmw_game_instance.countdown_total + 1)
    
    # Patch the actual database functions imported by the handler
    mock_add_xp = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.add_xp', new_callable=AsyncMock)

    await last_message_wins_handler.check_lmw_countdown(mock_context)
    
    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 1, 'player1', xp_to_add=10)
    mock_context.bot.send_message.assert_called_once() # Winner message
    mock_context.bot.pin_chat_message.assert_called_once()
    mock_context.bot.unpin_chat_message.assert_called_once()
    assert 'last_message_wins_game' not in mock_context.chat_data
    mock_context.job.schedule_removal.assert_called_once()

@pytest.mark.asyncio
async def test_check_lmw_countdown_no_winner(mock_context, lmw_game_instance, mocker):
    mocker.patch('time.time', return_value=100.0) # Initial time for setup

    lmw_game_instance.add_player(1, "player1") # Player joined but sent no message
    lmw_game_instance.start_countdown()
    lmw_game_instance.xp_pool = 10

    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    mock_context.job = MagicMock()
    mock_context.job.context = {'chat_id': lmw_game_instance.chat_id, 'game_message_id': lmw_game_instance.game_message_id}
    mock_context.job.schedule_removal = MagicMock()

    # Advance time to after countdown ends
    mocker.patch('time.time', return_value=100.0 + lmw_game_instance.countdown_total + 1)
    
    # Patch the actual database functions imported by the handler, though it shouldn't be called here
    mock_add_xp = mocker.patch('Yunks_game.handlers.last_message_wins_handler.db.add_xp', new_callable=AsyncMock)

    await last_message_wins_handler.check_lmw_countdown(mock_context)
    
    mock_add_xp.assert_not_called() # No XP awarded
    mock_context.bot.send_message.assert_called_once_with(chat_id=lmw_game_instance.chat_id, text="😔 Time's up, but no valid messages were sent! No winner this round.")
    assert 'last_message_wins_game' not in mock_context.chat_data
    mock_context.job.schedule_removal.assert_called_once()

@pytest.mark.asyncio
@patch('time.time', MagicMock(return_value=100.0))
async def test_check_lmw_countdown_mid_countdown(mock_context, lmw_game_instance, mocker):
    lmw_game_instance.add_player(1, "player1")
    lmw_game_instance.start_countdown()
    lmw_game_instance.record_message(1, "player1", 1001)

    mock_context.chat_data['last_message_wins_game'] = lmw_game_instance
    mock_context.job = MagicMock()
    mock_context.job.context = {'chat_id': lmw_game_instance.chat_id, 'game_message_id': lmw_game_instance.game_message_id}
    mock_context.job.schedule_removal = MagicMock()

    time.time.return_value = 100.0 + lmw_game_instance.countdown_total - 5 # 5 seconds left
    mocker.patch('Yunks_game.handlers.last_message_wins_handler.render_lmw_game', return_value=("Updated Text", InlineKeyboardMarkup([])))

    await last_message_wins_handler.check_lmw_countdown(mock_context)
    
    mock_context.bot.edit_message_text.assert_called_once_with(
        chat_id=lmw_game_instance.chat_id,
        message_id=lmw_game_instance.game_message_id,
        text="Updated Text",
        reply_markup=ANY,
        parse_mode='HTML'
    )
    mock_context.bot_data['db'].add_xp.assert_not_called()
    assert lmw_game_instance.status == LastMessageWinsStatus.COUNTDOWN
    mock_context.job.schedule_removal.assert_not_called() # Job should not be removed yet
