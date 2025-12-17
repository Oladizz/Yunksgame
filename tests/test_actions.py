import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
from telegram import Update
from telegram.ext import CallbackContext

from Yunks_game.handlers import actions
from Yunks_game import database

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object for action commands."""
    update = AsyncMock(spec=Update)
    update.effective_user.id = 123
    update.effective_user.username = 'actor_user'
    update.effective_user.mention_html = MagicMock(return_value='Actor User')
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()

    # Default reply_to_message for successful targeting
    update.message.reply_to_message = AsyncMock()
    update.message.reply_to_message.from_user.id = 456
    update.message.reply_to_message.from_user.username = 'target_user'
    update.message.reply_to_message.from_user.mention_html = MagicMock(return_value='Target User')
    update.message.reply_to_message.from_user.is_bot = False
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.user_data = {} # Initialize user_data for cooldown
    context.args = []
    
    # Make context.bot and its methods awaitable for strict_edit_message
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    return context

# --- /steal Command Tests ---

@pytest.mark.asyncio
async def test_steal_xp_success(mock_update, mock_context, mocker):
    """Test successful XP steal."""
    mocker.patch('random.random', return_value=0.2)
    mocker.patch('random.randint', return_value=10)
    mock_transfer = mocker.patch('Yunks_game.database.transfer_xp', new_callable=AsyncMock, return_value=True)

    await actions.steal_xp(mock_update, mock_context)

    mock_transfer.assert_called_once_with(
        mock_context.bot_data['db'], from_user_id=456, to_user_id=123, amount=10
    )
    mock_update.message.reply_html.assert_called_once()
    assert "Success" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_steal_xp_fail(mock_update, mock_context, mocker):
    """Test failed XP steal."""
    mocker.patch('random.random', return_value=0.8)
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)

    await actions.steal_xp(mock_update, mock_context)

    mock_add_xp.assert_called_once_with(
        mock_context.bot_data['db'], 123, 'actor_user', xp_to_add=-actions.STEAL_PENALTY
    )
    mock_update.message.reply_html.assert_called_once()
    assert "fumbled" in mock_update.message.reply_html.call_args[0][0]

# ... (other steal tests remain the same) ...

# --- /give Command Tests ---

@pytest.mark.asyncio
async def test_give_xp_success(mock_update, mock_context, mocker):
    """Test successful XP give."""
    mock_context.args = ['50']
    mocker.patch('Yunks_game.database.get_user_data', new_callable=AsyncMock, return_value={'xp': 100})
    mock_transfer_xp = mocker.patch('Yunks_game.database.transfer_xp', new_callable=AsyncMock, return_value=True)
    
    await actions.give_xp(mock_update, mock_context)
    
    mock_transfer_xp.assert_called_once_with(
        mock_context.bot_data['db'], from_user_id=123, to_user_id=456, amount=50
    )
    mock_update.message.reply_html.assert_called_once()
    assert "generously gave 50 XP" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_give_xp_insufficient_funds(mock_update, mock_context, mocker):
    """Test giving XP when the user doesn't have enough."""
    mock_context.args = ['150']
    mocker.patch('Yunks_game.database.get_user_data', new_callable=AsyncMock, return_value={'xp': 100})
    mock_transfer_xp = mocker.patch('Yunks_game.database.transfer_xp', new_callable=AsyncMock, return_value=False)

    await actions.give_xp(mock_update, mock_context)

    mock_transfer_xp.assert_not_called()
    mock_update.message.reply_text.assert_called_once_with("You don't have enough XP to give 150 away!")

@pytest.mark.asyncio
async def test_give_xp_no_reply(mock_update, mock_context):
    """Test /give without a reply."""
    mock_update.message.reply_to_message = None
    mock_context.args = ['50']
    
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("Please reply to a user's message to give them XP.")

@pytest.mark.asyncio
async def test_give_xp_to_self(mock_update, mock_context):
    """Test giving XP to oneself."""
    mock_update.message.reply_to_message.from_user.id = mock_update.effective_user.id
    mock_context.args = ['50']
    
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("You can't give XP to yourself.")

@pytest.mark.asyncio
async def test_give_xp_bad_args(mock_update, mock_context):
    """Test /give with invalid arguments."""
    mock_context.args = ['-50'] # Negative amount
    
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("You must give a positive amount of XP!")

    mock_update.message.reply_text.reset_mock() # Reset mock for the next assertion
    mock_context.args = [] # No amount
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("Usage: /give <amount>")

