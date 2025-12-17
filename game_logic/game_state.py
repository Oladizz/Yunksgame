from enum import Enum, auto
from typing import Dict, List, Optional
import time

class GamePhase(Enum):
    """Represents the current phase of the game."""
    LOBBY = auto()
    SEARCH = auto()
    RESULTS = auto()
    MOVEMENT = auto()
    SUSPICION = auto()
    ACCUSATION = auto()
    FARMERS_WIN = auto()
    RAT_WINS = auto()

class Game:
    """
    Holds the state for a single instance of the "Rat in the Farm" game.
    """
    def __init__(self, chat_id: int, owner_id: int, min_players: int = 1, max_players: int = 8):
        self.chat_id: int = chat_id
        self.owner_id: int = owner_id
        self.game_message_id: Optional[int] = None
        self.phase: GamePhase = GamePhase.LOBBY
        self.players: Dict[int, 'Player'] = {}
        self.rat_id: Optional[int] = None
        
        self.min_players: int = min_players
        self.max_players: int = max_players
        
        self.round_number: int = 0
        self.last_update_time: float = time.time()
        
        # Game-specific state
        self.farm: 'Farm' = None # To be initialized when the game starts

    def add_player(self, player: 'Player'):
        """Adds a player to the game."""
        if len(self.players) < self.max_players:
            self.players[player.user_id] = player
            return True
        return False

    def remove_player(self, user_id: int):
        """Removes a player from the game."""
        if user_id in self.players:
            del self.players[user_id]
            return True
        return False

    def get_player(self, user_id: int) -> Optional['Player']:
        """Gets a player by their user ID."""
        return self.players.get(user_id)
