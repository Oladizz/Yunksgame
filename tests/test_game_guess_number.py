import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update
from telegram.ext import CallbackContext
from yunks_game_2_0_1.handlers import game_guess_number
from yunks_game_2_0_1 import database

@pytest.fixture
def mock_admin_update():
    """Fixture for a mock Update object from an admin user."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    update.effective_chat = MagicMock()
    update.effective_chat.type = 'group'
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.user_data = {}
    context.bot = AsyncMock()
    admin_member = MagicMock()
    admin_member.user.id = 123
    context.bot.get_chat_administrators.return_value = [admin_member]
    return context

@pytest.mark.asyncio
@patch('random.randint', return_value=42)
async def test_start_new_game(mock_randint, mock_admin_update, mock_context):
    """Test the start of a new 'Guess the Number' game."""
    await game_guess_number.start_new_game(mock_admin_update, mock_context)

    mock_admin_update.message.reply_text.assert_called_once()
    assert "I'm thinking of a number" in mock_admin_update.message.reply_text.call_args[0][0]
    assert 'game' in mock_context.user_data
    assert mock_context.user_data['game']['secret_number'] == 42
    assert mock_context.user_data['game']['tries_left'] == 7

@pytest.mark.asyncio
async def test_handle_guess_correct(mock_admin_update, mock_context, mocker):
    """Test a correct guess."""
    mock_add_xp = mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)
    mock_context.user_data['game'] = {'secret_number': 42, 'tries_left': 5}
    mock_admin_update.message.text = '42'
    
    await game_guess_number.handle_guess(mock_admin_update, mock_context)
    
    mock_admin_update.message.reply_text.assert_called_once()
    assert "Congratulations! You guessed the number 42" in mock_admin_update.message.reply_text.call_args[0][0]
    assert 'game' not in mock_context.user_data
    mock_add_xp.assert_called_once()

@pytest.mark.asyncio
async def test_handle_guess_too_high(mock_admin_update, mock_context):
    """Test a guess that is too high."""
    mock_context.user_data['game'] = {'secret_number': 42, 'tries_left': 5}
    mock_admin_update.message.text = '50'
    
    await game_guess_number.handle_guess(mock_admin_update, mock_context)
    
    mock_admin_update.message.reply_text.assert_called_once_with("Too high! You have 4 tries left.")
    assert mock_context.user_data['game']['tries_left'] == 4

@pytest.mark.asyncio
async def test_handle_guess_too_low(mock_admin_update, mock_context):
    """Test a guess that is too low."""
    mock_context.user_data['game'] = {'secret_number': 42, 'tries_left': 5}
    mock_admin_update.message.text = '30'
    
    await game_guess_number.handle_guess(mock_admin_update, mock_context)
    
    mock_admin_update.message.reply_text.assert_called_once_with("Too low! You have 4 tries left.")
    assert mock_context.user_data['game']['tries_left'] == 4

@pytest.mark.asyncio
async def test_handle_guess_no_game(mock_admin_update, mock_context):
    """Test guessing without an active game."""
    mock_admin_update.message.text = '42'

    await game_guess_number.handle_guess(mock_admin_update, mock_context)

    mock_admin_update.message.reply_text.assert_called_once_with("You don't have an active game. Use /start_game to begin!")

@pytest.mark.asyncio
async def test_handle_guess_game_over(mock_admin_update, mock_context):
    """Test running out of tries."""
    mock_context.user_data['game'] = {'secret_number': 42, 'tries_left': 1}
    mock_admin_update.message.text = '50'
    
    await game_guess_number.handle_guess(mock_admin_update, mock_context)
    
    mock_admin_update.message.reply_text.assert_called_once_with("😔 Oh no! You ran out of tries. The secret number was 42.\n\nUse /start_game to play again.")
    assert 'game' not in mock_context.user_data