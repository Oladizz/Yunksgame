from enum import Enum, auto
from typing import Dict, Optional
import time

class LastMessageWinsStatus(Enum):
    LOBBY = auto()
    COUNTDOWN = auto()
    FINISHED = auto()

class LastMessageWinsGame:
    """
    Manages the state for a single instance of the "Last Message Wins" game.
    """
    def __init__(self, chat_id: int, owner_id: int, initial_countdown: int = 60, entry_xp_cost: int = 2):
        self.chat_id: int = chat_id
        self.owner_id: int = owner_id
        self.game_message_id: Optional[int] = None # To store the bot's main game message
        self.status: LastMessageWinsStatus = LastMessageWinsStatus.LOBBY
        self.players: Dict[int, str] = {} # {user_id: username} for players who joined
        self.xp_pool: int = 0
        self.entry_xp_cost: int = entry_xp_cost
        self.countdown_total: int = initial_countdown
        self.countdown_end_time: Optional[float] = None # Unix timestamp when countdown ends
        self.last_valid_message: Optional[Dict[str, any]] = None # {'user_id': int, 'username': str, 'message_id': int, 'timestamp': float}
        self.has_sent_message: Dict[int, bool] = {} # {user_id: True if sent a valid message}

    def add_player(self, user_id: int, username: str) -> bool:
        """Adds a player to the game lobby after collecting XP."""
        if self.status == LastMessageWinsStatus.LOBBY and user_id not in self.players:
            self.players[user_id] = username
            self.xp_pool += self.entry_xp_cost # Add to pool
            self.has_sent_message[user_id] = False # Reset for new game
            return True
        return False

    def remove_player(self, user_id: int) -> bool:
        """Removes a player from the game lobby."""
        if self.status == LastMessageWinsStatus.LOBBY and user_id in self.players:
            del self.players[user_id]
            self.xp_pool -= self.entry_xp_cost # Refund XP if in lobby
            del self.has_sent_message[user_id]
            return True
        return False

    def start_countdown(self) -> bool:
        """Starts the game countdown."""
        if self.status == LastMessageWinsStatus.LOBBY and len(self.players) > 0: # At least one player
            self.status = LastMessageWinsStatus.COUNTDOWN
            self.countdown_end_time = time.time() + self.countdown_total
            self.last_valid_message = None # Reset for current game
            return True
        return False

    def record_message(self, user_id: int, username: str, message_id: int) -> bool:
        """
        Records a valid message from a player.
        Returns True if the message is valid and recorded, False otherwise (e.g., already sent one).
        """
        if self.status == LastMessageWinsStatus.COUNTDOWN and user_id in self.players:
            if not self.has_sent_message.get(user_id, False):
                self.last_valid_message = {
                    'user_id': user_id,
                    'username': username,
                    'message_id': message_id,
                    'timestamp': time.time()
                }
                self.has_sent_message[user_id] = True
                return True
        return False

    def is_countdown_over(self) -> bool:
        """Checks if the countdown has finished."""
        return self.countdown_end_time is not None and time.time() >= self.countdown_end_time

    def determine_winner(self) -> Optional[Dict[str, any]]:
        """Determines the winner once the countdown is over."""
        if self.status == LastMessageWinsStatus.COUNTDOWN and self.is_countdown_over():
            self.status = LastMessageWinsStatus.FINISHED
            return self.last_valid_message
        return None

    def reset_game(self):
        """Resets the game to its initial lobby state."""
        self.status = LastMessageWinsStatus.LOBBY
        self.players = {}
        self.xp_pool = 0
        self.countdown_end_time = None
        self.last_valid_message = None
        self.has_sent_message = {}
