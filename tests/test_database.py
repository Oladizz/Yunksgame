import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import firebase_admin
import asyncio

import database

@pytest.fixture
def mock_db():
    """Fixture to create a mock database client."""
    db_mock = MagicMock()
    # Mock the transaction object that the `db` client creates
    db_mock.transaction.return_value = MagicMock()
    return db_mock

@pytest.fixture
def mock_transaction():
    """Fixture for a mock Firestore transaction."""
    return MagicMock()

@pytest.mark.asyncio
async def test_init_firebase(mocker):
    """Test Firebase initialization."""
    mocker.patch('firebase_admin.credentials.Certificate', return_value=None)
    mocker.patch('firebase_admin.initialize_app', return_value=None)
    mocker.patch('firebase_admin.firestore.client', return_value=MagicMock())
    mocker.patch('firebase_admin._apps', [])
    db_client = database.init_firebase('dummy_path')
    assert db_client is not None
    firebase_admin.initialize_app.assert_called_once()

@pytest.mark.asyncio
async def test_add_xp_calls_transactional_function(mocker, mock_db):
    """Test that add_xp calls the underlying transactional function."""
    user_id = 'test_user'
    username = 'test_username'
    xp_to_add = 10
    
    # Patch the transactional function directly
    mock_sync_transaction = mocker.patch('database._add_xp_sync_transaction')

    await database.add_xp(mock_db, user_id, username, xp_to_add)

    # Assert that our transactional function was called with the correct arguments
    mock_sync_transaction.assert_called_once()
    # The first argument is the transaction object, which we can check for existence
    assert mock_sync_transaction.call_args[0][0] is not None 
    # Check the rest of the arguments
    assert mock_sync_transaction.call_args[0][1:] == (mock_db, user_id, username, xp_to_add)


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