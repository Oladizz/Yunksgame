from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from Yunks_game.admin_dashboard.backend.main import app, get_db

# --- Mocks and Fixtures ---

# Create a mock database client to be used in tests
mock_db_client = MagicMock()

def override_get_db():
    """A dependency override that returns the mock client."""
    return mock_db_client

# Apply the dependency override to the app for all tests
app.dependency_overrides[get_db] = override_get_db


def test_read_root():
    """Test the root endpoint."""
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

def test_get_users(mocker):
    """Test the /api/users endpoint with a mocked database."""
    mock_users = [('user1', 100), ('user2', 200)]
    # Patch the get_leaderboard function at its source
    mock_get_leaderboard = mocker.patch('Yunks_game.database.get_leaderboard', return_value=mock_users)
    
    expected_json = {"users": [['user1', 100], ['user2', 200]]}
    
    with TestClient(app) as client:
        response = client.get("/api/users")
        
        assert response.status_code == 200
        assert response.json() == expected_json
        mock_get_leaderboard.assert_called_once_with(mock_db_client, limit=1000)

