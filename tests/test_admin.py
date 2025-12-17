import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from unittest.mock import MagicMock, AsyncMock, patch

from Yunks_game.handlers import admin
from Yunks_game import database

@pytest.fixture
def mock_admin_update():
    """Fixture for a mock Update from an admin user."""
    update = AsyncMock()
    update.effective_user.id = 12345 # An admin ID
    update.message = AsyncMock()
    update.message.reply_to_message.from_user.id = 67890
    update.message.reply_to_message.from_user.username = "test_recipient"
    return update

@pytest.fixture
def mock_non_admin_update():
    """Fixture for a mock Update from a non-admin user."""
    update = AsyncMock()
    update.effective_user.id = 99999 # A non-admin ID
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    """Fixture for a mock CallbackContext object."""
    context = MagicMock()
    context.bot_data = {'db': MagicMock()}
    context.args = []
    
    # Make context.bot and its methods awaitable
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock() # Used by reply_text
    return context

@pytest.mark.asyncio
@patch('Yunks_game.handlers.admin.ADMIN_USER_IDS', [12345]) # Mock the admin IDs
async def test_award_xp_success(mock_admin_update, mock_context, mocker):
    """Test successful XP award by an admin."""
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)
    mock_context.args = ['100']
    
    await admin.award_xp(mock_admin_update, mock_context)
    
    mock_add_xp.assert_called_once_with(mock_context.bot_data['db'], 67890, "test_recipient", xp_to_add=100)
    mock_admin_update.message.reply_text.assert_called_once_with("Successfully awarded 100 XP to @test_recipient.")

@pytest.mark.asyncio
@patch('Yunks_game.handlers.admin.ADMIN_USER_IDS', [12345])
async def test_award_xp_non_admin(mock_non_admin_update, mock_context, mocker):
    """Test non-admin attempting to use /awardxp."""
    mock_add_xp = mocker.patch('Yunks_game.database.add_xp', new_callable=AsyncMock)
    mock_context.args = ['100']

    await admin.award_xp(mock_non_admin_update, mock_context)
    
    mock_add_xp.assert_not_called()
    mock_non_admin_update.message.reply_text.assert_called_once_with("This is an admin-only command.")

@pytest.mark.asyncio
@patch('Yunks_game.handlers.admin.ADMIN_USER_IDS', [12345])
async def test_award_xp_no_reply(mock_admin_update, mock_context):
    """Test /awardxp without a reply."""
    mock_admin_update.message.reply_to_message = None
    mock_context.args = ['100']

    await admin.award_xp(mock_admin_update, mock_context)
    mock_admin_update.message.reply_text.assert_called_once_with("Please reply to a user's message to award them XP.")

@pytest.mark.asyncio
@patch('Yunks_game.handlers.admin.ADMIN_USER_IDS', [12345])
async def test_award_xp_bad_args(mock_admin_update, mock_context):
    """Test /awardxp with invalid arguments."""
    mock_context.args = ['one_hundred'] # Invalid amount

    await admin.award_xp(mock_admin_update, mock_context)
    mock_admin_update.message.reply_text.assert_called_once_with("Usage: /awardxp <amount>")
