import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import firebase_admin

from Yunks_game import database

@pytest.fixture
def mock_db():
    """Fixture to create a mock database client."""
    return MagicMock()

def test_init_firebase(mocker):
    """Test Firebase initialization."""
    mocker.patch('firebase_admin.credentials.Certificate', return_value=None)
    mocker.patch('firebase_admin.initialize_app', return_value=None)
    mocker.patch('firebase_admin.firestore.client', return_value=MagicMock())
    mocker.patch('firebase_admin._apps', [])
    db_client = database.init_firebase('dummy_path')
    assert db_client is not None
    firebase_admin.initialize_app.assert_called_once()

def test_get_user_data_exists(mock_db):
    """Test getting user data for an existing user."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {'username': 'testuser', 'xp': 100}
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    user_data = database.get_user_data(mock_db, '123')
    assert user_data is not None
    assert user_data['username'] == 'testuser'
    assert user_data['xp'] == 100

def test_get_user_data_not_exists(mock_db):
    """Test getting user data for a non-existent user."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    user_data = database.get_user_data(mock_db, '123')
    assert user_data is None

def test_add_xp(mock_db):
    """Test adding XP."""
    mock_transaction = MagicMock()
    mock_db.transaction.return_value = mock_transaction
    
    with patch('Yunks_game.database._add_xp_transaction') as mock_transactional_func:
        database.add_xp(mock_db, '123', 'newuser', 10)
        mock_transactional_func.assert_called_once()

def test_get_leaderboard(mock_db):
    """Test getting the leaderboard."""
    mock_doc1 = MagicMock()
    mock_doc1.to_dict.return_value = {'username': 'user1', 'xp': 100}
    mock_doc2 = MagicMock()
    mock_doc2.to_dict.return_value = {'username': 'user2', 'xp': 200}
    
    mock_query = MagicMock()
    mock_query.stream.return_value = [mock_doc2, mock_doc1] # Ordered by XP descending
    
    mock_db.collection.return_value.order_by.return_value.limit.return_value = mock_query

    leaderboard = database.get_leaderboard(mock_db)
    assert leaderboard == [('user2', 200), ('user1', 100)]

@pytest.mark.asyncio
async def test_transfer_xp_success(mock_db, mocker):
    """Test successful XP transfer."""
    mock_transaction_instance = AsyncMock()
    mock_db.transaction.return_value = mock_transaction_instance # Ensure mock_db.transaction returns an AsyncMock
    mocker.patch('Yunks_game.database._transfer_xp_transaction', new_callable=AsyncMock, return_value=True)

    result = await database.transfer_xp(mock_db, 'user1', 'user2', 50)
    assert result is True
    database._transfer_xp_transaction.assert_called_once_with(mock_transaction_instance, mock_db, 'user1', 'user2', 50)

@pytest.mark.asyncio
async def test_transfer_xp_insufficient_funds(mock_db, mocker):
    """Test XP transfer with insufficient funds."""
    mock_transaction_instance = AsyncMock()
    mock_db.transaction.return_value = mock_transaction_instance # Ensure mock_db.transaction returns an AsyncMock
    mocker.patch('Yunks_game.database._transfer_xp_transaction', new_callable=AsyncMock, return_value=False)

    result = await database.transfer_xp(mock_db, 'user1', 'user2', 150) # user1 only has 100 XP in mock
    assert result is False
    database._transfer_xp_transaction.assert_called_once_with(mock_transaction_instance, mock_db, 'user1', 'user2', 150)

@pytest.mark.asyncio
async def test_transfer_xp_transaction_success(mock_db, mocker):
    """Test the _transfer_xp_transaction function for a successful transfer."""
    mock_transaction = MagicMock() # Transaction object is not async itself for update/set operations directly
    
    from_user_ref = MagicMock()
    to_user_ref = MagicMock()
    
    from_doc = MagicMock()
    from_doc.exists = True
    from_doc.to_dict.return_value = {'xp': 100}
    
    to_doc = MagicMock()
    to_doc.exists = True
    to_doc.to_dict.return_value = {'xp': 50}

    from_user_ref.get = AsyncMock(return_value=from_doc)
    to_user_ref.get = AsyncMock(return_value=to_doc)

    mock_db.collection.return_value.document.side_effect = [from_user_ref, to_user_ref]

    # No need to patch database.db as it's passed as an argument
    result = await database._transfer_xp_transaction(mock_transaction, mock_db, 'user1', 'user2', 30)
    assert result is True
    from_user_ref.get.assert_called_with(transaction=mock_transaction)
    to_user_ref.get.assert_called_with(transaction=mock_transaction)
    mock_transaction.update.assert_any_call(from_user_ref, {'xp': 70})
    mock_transaction.update.assert_any_call(to_user_ref, {'xp': 80})

@pytest.mark.asyncio
async def test_transfer_xp_transaction_insufficient_xp(mock_db, mocker):
    """Test _transfer_xp_transaction when the sender has insufficient XP."""
    mock_transaction = MagicMock()
    
    from_user_ref = MagicMock()
    to_user_ref = MagicMock()
    
    from_doc = MagicMock()
    from_doc.exists = True
    from_doc.to_dict.return_value = {'xp': 20} # Insufficient XP
    
    to_doc = MagicMock()
    to_doc.exists = True
    to_doc.to_dict.return_value = {'xp': 50}

    from_user_ref.get = AsyncMock(return_value=from_doc)
    to_user_ref.get = AsyncMock(return_value=to_doc)

    mock_db.collection.return_value.document.side_effect = [from_user_ref, to_user_ref]

    result = await database._transfer_xp_transaction(mock_transaction, mock_db, 'user1', 'user2', 30)
    assert result is False
    from_user_ref.get.assert_called_with(transaction=mock_transaction)
    to_user_ref.get.assert_called_with(transaction=mock_transaction)
    mock_transaction.update.assert_not_called()

@pytest.mark.asyncio
async def test_transfer_xp_transaction_user_not_exists(mock_db, mocker):
    """Test _transfer_xp_transaction when one of the users does not exist."""
    mock_transaction = MagicMock()
    
    from_user_ref = MagicMock()
    to_user_ref = MagicMock()
    
    from_doc = MagicMock()
    from_doc.exists = False # User does not exist
    
    to_doc = MagicMock()
    to_doc.exists = True
    to_doc.to_dict.return_value = {'xp': 50}

    from_user_ref.get = AsyncMock(return_value=from_doc)
    to_user_ref.get = AsyncMock(return_value=to_doc)

    mock_db.collection.return_value.document.side_effect = [from_user_ref, to_user_ref]

    result = await database._transfer_xp_transaction(mock_transaction, mock_db, 'user1', 'user2', 30)
    assert result is False
    from_user_ref.get.assert_called_with(transaction=mock_transaction)
    # to_user_ref.get should still be called to check for its existence
    to_user_ref.get.assert_called_with(transaction=mock_transaction)
    mock_transaction.update.assert_not_called()

