import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
from telegram import Update
from telegram.ext import CallbackContext
from yunks_game_2_0_1.handlers import actions
from yunks_game_2_0_1 import database

@pytest.fixture
def mock_update():
    """Fixture for a mock Update object for action commands."""
    update = AsyncMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.effective_user.username = 'giver'
    update.effective_user.mention_html.return_value = "Giver"
    
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()
    
    # Mock effective_chat type for decorator tests
    update.effective_chat.type = 'group' # Default to group for admin checks
    
    # Simulate a reply to another user
    reply_user = MagicMock()
    reply_user.id = 456
    reply_user.username = 'receiver'
    reply_user.is_bot = False
    reply_user.mention_html.return_value = "Receiver"
    
    # Correctly mock the nested structure
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.from_user = reply_user
    
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock(spec=CallbackContext)
    context.bot_data = {'db': MagicMock()}
    context.args = []
    context.user_data = {}
    
    # Mock context.bot and its methods for the is_admin decorator
    context.bot = AsyncMock()
    context.bot.id = 789
    # Mock get_chat_administrators to return the effective user as an admin by default
    admin_member = MagicMock()
    admin_member.user.id = 123 # Assuming 123 is the default effective_user.id for admin tests
    context.bot.get_chat_administrators.return_value = [admin_member]

    return context

@pytest.mark.asyncio
async def test_give_xp_success(mock_update, mock_context, mocker):
    """Test a successful XP transfer."""
    mock_context.args = ['50']
    mocker.patch('yunks_game_2_0_1.database.get_user_data', new_callable=AsyncMock, return_value={'xp': 100})
    mock_transfer = mocker.patch('yunks_game_2_0_1.database.transfer_xp', new_callable=AsyncMock, return_value=True)

    await actions.give_xp(mock_update, mock_context)

    database.get_user_data.assert_called_once_with(mock_context.bot_data['db'], 123)
    mock_transfer.assert_called_once_with(mock_context.bot_data['db'], from_user_id=123, to_user_id=456, amount=50)
    mock_update.message.reply_html.assert_called_once()
    assert "generously gave 50 XP" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_give_xp_insufficient_funds(mock_update, mock_context, mocker):
    """Test trying to give more XP than available."""
    mock_context.args = ['150']
    mocker.patch('yunks_game_2_0_1.database.get_user_data', new_callable=AsyncMock, return_value={'xp': 100})
    mock_transfer = mocker.patch('yunks_game_2_0_1.database.transfer_xp')

    await actions.give_xp(mock_update, mock_context)

    mock_transfer.assert_not_called()
    mock_update.message.reply_text.assert_called_once_with("You don't have enough XP to give 150 away!")

@pytest.mark.asyncio
async def test_give_xp_no_reply(mock_update, mock_context):
    """Test /give without replying to a user."""
    mock_update.message.reply_to_message = None
    
    await actions.give_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("Please reply to a user's message to give them XP.")

@pytest.mark.asyncio
async def test_give_xp_to_self(mock_update, mock_context):
    """Test giving XP to oneself."""
    mock_context.args = ['50']
    mock_update.message.reply_to_message.from_user.id = 123 # Giver is also the receiver

    await actions.give_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("You can't give XP to yourself.")

@pytest.mark.asyncio
async def test_give_xp_invalid_amount(mock_update, mock_context):
    """Test giving an invalid amount of XP."""
    mock_context.args = ['-50']
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("You must give a positive amount of XP!")

@pytest.mark.asyncio
async def test_give_xp_non_numeric_amount(mock_update, mock_context):
    """Test giving a non-numeric amount of XP."""
    mock_context.args = ['abc']
    await actions.give_xp(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("Usage: /give <amount>")

# --- Steal Tests ---

@pytest.mark.asyncio
async def test_steal_xp_success(mock_update, mock_context, mocker):
    """Test a successful steal."""
    mocker.patch('random.random', return_value=0.4) # Success
    mocker.patch('random.randint', return_value=10)
    mock_transfer = mocker.patch('yunks_game_2_0_1.database.transfer_xp', new_callable=AsyncMock, return_value=True)

    await actions.steal_xp(mock_update, mock_context)

    mock_transfer.assert_called_once_with(mock_context.bot_data['db'], from_user_id=456, to_user_id=123, amount=10)
    mock_update.message.reply_html.assert_called_once()
    assert "masterfully swiped 10 XP" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_steal_xp_failure(mock_update, mock_context, mocker):
    """Test a failed steal."""
    mocker.patch('random.random', return_value=0.6) # Fail
    mocker.patch('yunks_game_2_0_1.database.transfer_xp', new_callable=AsyncMock, return_value=False)
    mock_add_xp = mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

    await actions.steal_xp(mock_update, mock_context)

    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 123, 'giver', xp_to_add=-5)
    mock_update.message.reply_html.assert_called_once()
    assert "fumbled the attempt" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_steal_xp_cooldown(mock_update, mock_context):
    """Test steal command on cooldown."""
    mock_context.user_data['last_steal'] = time.time() - 1700 # 1700 seconds ago, so still in cooldown
    
    await actions.steal_xp(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    assert "on cooldown" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_steal_xp_no_reply(mock_update, mock_context):
    """Test /steal without a reply."""
    mock_update.message.reply_to_message = None
    
    await actions.steal_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("To steal XP, you must reply to a message from the user you want to rob.")

@pytest.mark.asyncio
async def test_award_xp_success(mock_update, mock_context, mocker):
    """Test a successful XP award by an admin."""
    mock_context.args = ['100']
    mock_add_xp = mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

    await actions.award_xp(mock_update, mock_context)

    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 456, 'receiver', xp_to_add=100)
    mock_update.message.reply_html.assert_called_once()
    assert "awarded 100 XP" in mock_update.message.reply_html.call_args[0][0]

@pytest.mark.asyncio
async def test_award_xp_no_reply(mock_update, mock_context):
    """Test /awardxp without replying to a user."""
    mock_update.message.reply_to_message = None
    mock_context.args = ['50']
    
    await actions.award_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("Please reply to a user's message to award them XP.")

@pytest.mark.asyncio
async def test_award_xp_invalid_amount(mock_update, mock_context):
    """Test /awardxp with an invalid amount (non-positive)."""
    mock_context.args = ['-10']
    
    await actions.award_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("You must award a positive amount of XP!")

@pytest.mark.asyncio
async def test_award_xp_non_numeric_amount(mock_update, mock_context):
    """Test /awardxp with a non-numeric amount."""
    mock_context.args = ['abc']
    
    await actions.award_xp(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("Usage: /awardxp <amount> (reply to user)")

@pytest.mark.asyncio
async def test_award_xp_to_bot(mock_update, mock_context):
    """Test /awardxp when replying to a bot."""
    mock_update.message.reply_to_message.from_user.is_bot = True
    mock_context.args = ['50']

    await actions.award_xp(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once_with("Bots don't need XP.")

# --- End Game Tests ---

@pytest.mark.asyncio
async def test_end_game_active_game(mock_update, mock_context):
    """Test ending an active game."""
    mock_context.user_data['game'] = {'secret_number': 50, 'tries_left': 5}
    mock_update.effective_chat.id = 12345 # Example chat ID

    await actions.end_game(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once_with("The active game has been ended.")
    assert 'game' not in mock_context.user_data

@pytest.mark.asyncio
async def test_end_game_no_active_game(mock_update, mock_context):
    """Test ending game when no game is active."""
    mock_update.effective_chat.id = 12345 # Example chat ID
    # Ensure no 'game' in user_data
    if 'game' in mock_context.user_data:
        del mock_context.user_data['game']

    await actions.end_game(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once_with("No active game found in this chat for you to end.")
    assert 'game' not in mock_context.user_data

@pytest.mark.asyncio
async def test_steal_from_bot_success(mock_update, mock_context, mocker):
    """Test a successful steal from the bot."""
    mocker.patch('random.random', return_value=0.4) # Success
    mocker.patch('random.randint', return_value=10)
    mock_add_xp = mocker.patch('yunks_game_2_0_1.database.add_xp', new_callable=AsyncMock)

    mock_update.message.reply_to_message.from_user.is_bot = True
    mock_update.message.reply_to_message.from_user.id = mock_context.bot.id

    await actions.steal_xp(mock_update, mock_context)

    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 123, 'giver', xp_to_add=10)
    mock_update.message.reply_html.assert_called_once()
    assert "masterfully swiped 10 XP from the bot!" in mock_update.message.reply_html.call_args[0][0]