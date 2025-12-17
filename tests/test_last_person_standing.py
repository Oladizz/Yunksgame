import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, JobQueue
import time

from Yunks_game.game_logic.last_person_standing import LastPersonStanding, GameStatus, EliminationReason
from Yunks_game.game_logic.player import Player
from Yunks_game.handlers import last_person_standing_handler
from Yunks_game import database as db

# --- Fixtures ---

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.effective_user.username = 'testuser'
    update.effective_user.mention_html.return_value = 'Test User'
    update.message = AsyncMock()
    update.message.chat_id = 12345
    update.message.message_id = 67890
    update.message.reply_text = AsyncMock()
    
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
    context.bot_data = {'db': MagicMock()}
    context.bot_data['db'].add_xp = AsyncMock() # Explicitly make add_xp an AsyncMock
    context.bot_data['db'].get_user_data = AsyncMock() # Also make get_user_data an AsyncMock if used
    context.chat_data = {}
    context.user_data = {}
    
    # Mock job_queue
    context.job_queue = MagicMock(spec=JobQueue)
    context.job_queue.run_once = MagicMock()

    # Mock bot for strict_edit_message
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock()
    return context

@pytest.fixture
def lps_game_instance():
    """Fixture for a LastPersonStanding game instance."""
    game = LastPersonStanding(chat_id=12345, owner_id=123)
    game.add_player(Player(game.owner_id, "owneruser")) # Add owner as a player
    return game

# --- Test LastPersonStanding Class ---

def test_lps_init(lps_game_instance):
    assert lps_game_instance.chat_id == 12345
    assert lps_game_instance.owner_id == 123
    assert lps_game_instance.status == GameStatus.LOBBY
    assert len(lps_game_instance.players) == 1 # Owner is added by fixture

def test_lps_add_player(lps_game_instance):
    # Owner is already player 123
    player2 = Player(1, "p1") # Use a different ID than owner
    lps_game_instance.add_player(player2)
    assert len(lps_game_instance.players) == 2
    assert lps_game_instance.get_player(1) == player2

    # Cannot add same player twice
    lps_game_instance.add_player(player2)
    assert len(lps_game_instance.players) == 2

def test_lps_remove_player(lps_game_instance):
    # Owner is already in game
    player_to_remove = Player(1, "p1")
    lps_game_instance.add_player(player_to_remove)
    lps_game_instance.remove_player(1)
    assert len(lps_game_instance.players) == 1 # Only owner remains
    assert lps_game_instance.get_player(1) is None

def test_lps_start_game_success(lps_game_instance):
    # Owner is already added
    lps_game_instance.add_player(Player(2, "p2"))
    lps_game_instance.add_player(Player(3, "p3"))
    assert lps_game_instance.start_game() is True
    assert lps_game_instance.status == GameStatus.RUNNING

def test_lps_start_game_fail_not_enough_players(lps_game_instance):
    # Only owner is in game (1 player), need 3 to start
    assert lps_game_instance.start_game() is False
    assert lps_game_instance.status == GameStatus.LOBBY

def test_lps_eliminate_random_player(lps_game_instance, mocker):
    mocker.patch('random.choice', side_effect=[1, EliminationReason.BAD_CODE_COMMIT])
    # Owner is already player 123
    lps_game_instance.add_player(Player(1, "p1"))
    lps_game_instance.add_player(Player(2, "p2"))
    lps_game_instance.add_player(Player(3, "p3"))
    lps_game_instance.add_player(Player(4, "p4"))
    lps_game_instance.status = GameStatus.RUNNING # Manually set status for test
    
    eliminated, reason = lps_game_instance.eliminate_random_player()
    # Mocked random.choice returns 1, so Player(1,"p1") is eliminated.
    assert eliminated.user_id == 1
    assert reason == EliminationReason.BAD_CODE_COMMIT
    assert len(lps_game_instance.players) == 4 # Initial 5 players, 1 eliminated
    assert eliminated in lps_game_instance.eliminated_players

def test_lps_get_winners(lps_game_instance):
    # Owner is already added
    lps_game_instance.add_player(Player(2, "p2"))
    lps_game_instance.add_player(Player(3, "p3"))
    lps_game_instance.status = GameStatus.RUNNING
    
    winners = lps_game_instance.get_winners()
    assert len(winners) == 3
    assert lps_game_instance.status == GameStatus.FINISHED

# --- Test Handlers ---

@pytest.mark.asyncio
async def test_start_lps_game_command(mock_update, mock_context, mocker):
    mock_update.callback_query = None # Simulate command
    mocker.patch('Yunks_game.handlers.last_person_standing_handler.render_lps_game', return_value=("text", InlineKeyboardMarkup([])))
    
    await last_person_standing_handler.start_lps_game(mock_update, mock_context)
    
    assert 'last_person_standing_game' in mock_context.chat_data
    game = mock_context.chat_data['last_person_standing_game']
    assert game.owner_id == mock_update.effective_user.id
    mock_context.bot.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_handle_lps_callback_join(mock_update, mock_context, lps_game_instance, mocker):
    mock_update.callback_query.data = 'lps_join'
    mock_update.callback_query.from_user.id = 456
    mock_update.callback_query.from_user.username = 'newplayer'
    mock_context.chat_data['last_person_standing_game'] = lps_game_instance
    mocker.patch('Yunks_game.handlers.last_person_standing_handler.strict_edit_message', new_callable=AsyncMock)

    await last_person_standing_handler.handle_lps_callback(mock_update, mock_context)
    
    assert len(lps_game_instance.players) == 2 # Owner + new player
    assert lps_game_instance.get_player(456).username == 'newplayer'
    mock_update.callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_handle_lps_callback_start_game(mock_update, mock_context, lps_game_instance, mocker):
    # Add enough players (owner is already 1)
    lps_game_instance.add_player(Player(101, "p1"))
    lps_game_instance.add_player(Player(102, "p2"))
    # Now 3 players: owner(123), p1(101), p2(102)
    mock_update.callback_query.data = 'lps_start_game'
    mock_update.callback_query.from_user.id = lps_game_instance.owner_id # Owner starts
    mock_context.chat_data['last_person_standing_game'] = lps_game_instance
    mocker.patch('Yunks_game.handlers.last_person_standing_handler.strict_edit_message', new_callable=AsyncMock)
    
    await last_person_standing_handler.handle_lps_callback(mock_update, mock_context)
    
    assert lps_game_instance.status == GameStatus.RUNNING
    mock_context.job_queue.run_once.assert_called_once()
    mock_context.bot.send_message.assert_called_once_with(chat_id=lps_game_instance.chat_id, text="The game begins! Eliminating players soon...")

@pytest.mark.asyncio
async def test_initiate_elimination_loop_awards_xp(mock_context, lps_game_instance, mocker):
    # Setup game with 3 players remaining to trigger win condition
    # Owner is already 123
    lps_game_instance.add_player(Player(1, "p1"))
    lps_game_instance.add_player(Player(2, "p2"))
    lps_game_instance.status = GameStatus.RUNNING
    
    mock_context.chat_data['last_person_standing_game'] = lps_game_instance
    mock_context.job = MagicMock()
    mock_context.job.data = {'chat_id': lps_game_instance.chat_id, 'game_message_id': lps_game_instance.game_message_id}

    mocker.patch('Yunks_game.handlers.last_person_standing_handler.strict_edit_message', new_callable=AsyncMock)
    mocker.patch('random.choice', return_value=EliminationReason.COULDNT_MAKE_IT) # Mock elimination reason
    
    # Ensure eliminate_random_player returns None if <= 3 players
    mocker.patch.object(lps_game_instance, 'eliminate_random_player', return_value=None)
    
    # Mock the actual database.add_xp function that initiate_elimination_loop calls
    mock_db_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)
    
    await last_person_standing_handler.initiate_elimination_loop(mock_context)
    
    # Check if XP was awarded
    assert mock_db_add_xp.call_count == 3
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], lps_game_instance.get_player(123).user_id, lps_game_instance.get_player(123).username, xp_to_add=last_person_standing_handler.XP_AWARD_PER_WINNER)
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], lps_game_instance.get_player(1).user_id, lps_game_instance.get_player(1).username, xp_to_add=last_person_standing_handler.XP_AWARD_PER_WINNER)
    mock_db_add_xp.assert_any_call(mock_context.bot_data['db'], lps_game_instance.get_player(2).user_id, lps_game_instance.get_player(2).username, xp_to_add=last_person_standing_handler.XP_AWARD_PER_WINNER)
    
    mock_context.bot.send_message.assert_called_once() # For final message
    assert 'THE WINNERS ARE IN!' in mock_context.bot.send_message.call_args[1]['text']
    assert 'last_person_standing_game' not in mock_context.chat_data # Game state cleared

@pytest.mark.asyncio
async def test_initiate_elimination_loop_eliminates_player(mock_context, lps_game_instance, mocker):
    # Setup game with >3 players
    # Owner is already 123
    p1 = Player(1, "p1")
    p2 = Player(2, "p2")
    p3 = Player(3, "p3")
    p4 = Player(4, "p4")
    lps_game_instance.add_player(p1)
    lps_game_instance.add_player(p2)
    lps_game_instance.add_player(p3)
    lps_game_instance.add_player(p4)
    lps_game_instance.status = GameStatus.RUNNING
    
    mock_context.chat_data['last_person_standing_game'] = lps_game_instance
    mock_context.job = MagicMock()
    mock_context.job.data = {'chat_id': lps_game_instance.chat_id, 'game_message_id': lps_game_instance.game_message_id}

    mocker.patch('Yunks_game.handlers.last_person_standing_handler.strict_edit_message', new_callable=AsyncMock)
    mocker.patch('random.choice', side_effect=[4, EliminationReason.FELL_OFF_CLIFF]) # Mock choice for eliminated player ID and reason
    
    # Mock the actual database.add_xp function, though it shouldn't be called here
    mock_db_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)

    await last_person_standing_handler.initiate_elimination_loop(mock_context)
    
    assert len(lps_game_instance.players) == 4 # One player eliminated (5 total - 1 eliminated = 4)
    assert p4 not in lps_game_instance.players.values()
    assert mock_context.bot.send_message.call_count == 1 # Only elimination message, not win message
    assert 'fell off a cliff' in mock_context.bot.send_message.call_args[1]['text']
    mock_context.job_queue.run_once.assert_called_once() # Next elimination scheduled