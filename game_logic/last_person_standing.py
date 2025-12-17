from enum import Enum, auto
from typing import Dict, Optional, List, Tuple
import random
import time

class GameStatus(Enum):
    LOBBY = auto()
    RUNNING = auto()
    FINISHED = auto()

class EliminationReason(Enum):
    FELL_OFF_CLIFF = "fell off a cliff while chasing a butterfly."
    EATEN_BY_GRUE = "was eaten by a Grue."
    BAD_CODE_COMMIT = "pushed a bad code commit to production."
    FORGOT_SEMICOLON = "forgot a semicolon and the universe imploded around them."
    TOO_MUCH_COFFEE = "drank too much coffee and ascended to another dimension."
    COULDNT_MAKE_IT = "couldn't make it to the final round." # Generic reason for user's request

class LastPersonStanding:
    """
    Manages the state for a single instance of the "Last Person Standing" game.
    """
    def __init__(self, chat_id: int, owner_id: int):
        self.chat_id: int = chat_id
        self.owner_id: int = owner_id
        self.game_message_id: Optional[int] = None
        self.status: GameStatus = GameStatus.LOBBY
        self.players: Dict[int, 'Player'] = {} # Active players
        self.eliminated_players: List['Player'] = [] # Players who have been eliminated
        self.last_update_time: float = time.time()
        self.min_players_to_start = 1 # Minimum players to start the game
        self.last_players_count = 3 # Number of players to award XP

    def add_player(self, player: 'Player'):
        """Adds a player to the game lobby."""
        if self.status == GameStatus.LOBBY and player.user_id not in self.players:
            self.players[player.user_id] = player
            return True
        return False

    def remove_player(self, user_id: int):
        """Removes a player from the game."""
        if user_id in self.players:
            if self.status == GameStatus.LOBBY:
                del self.players[user_id]
                return True
            # Cannot remove players once game has started unless they are eliminated
            return False
        return False

    def get_player(self, user_id: int) -> Optional['Player']:
        """Gets a player by their user ID."""
        return self.players.get(user_id)

    def start_game(self):
        """Starts the game, moving from LOBBY to RUNNING."""
        if self.status == GameStatus.LOBBY and len(self.players) >= self.min_players_to_start:
            self.status = GameStatus.RUNNING
            self.eliminated_players = [] # Clear any previous eliminations
            return True
        return False

    def eliminate_random_player(self) -> Optional[Tuple['Player', EliminationReason]]:
        """
        Randomly eliminates a player from the active players.
        Returns the eliminated player and the reason, or None if no players to eliminate.
        """
        if self.status == GameStatus.RUNNING and len(self.players) > self.last_players_count:
            player_ids = list(self.players.keys())
            if not player_ids:
                return None
            
            eliminated_id = random.choice(player_ids)
            eliminated_player = self.players.pop(eliminated_id)
            
            # Select a random elimination reason
            reason = random.choice(list(EliminationReason))
            
            self.eliminated_players.append(eliminated_player)
            return eliminated_player, reason
        return None

    def get_remaining_players_count(self) -> int:
        """Returns the number of players still active in the game."""
        return len(self.players)

    def get_winners(self) -> List['Player']:
        """Returns the list of winning players."""
        # If the game is running and the number of players is <= the target winner count, these are the winners.
        if self.status == GameStatus.RUNNING and len(self.players) <= self.last_players_count:
            self.status = GameStatus.FINISHED
            return list(self.players.values())
        return []

    def is_game_finished(self) -> bool:
        """Checks if the game has concluded."""
        return self.status == GameStatus.FINISHED

    def reset_game(self):
        """Resets the game to its initial lobby state."""
        self.status = GameStatus.LOBBY
        self.players = {}
        self.eliminated_players = []
        self.game_message_id = None
        self.last_update_time = time.time()
