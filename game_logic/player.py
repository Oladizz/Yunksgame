from enum import Enum, auto

class Role(Enum):
    """Represents the player's role in the game."""
    FARMER = auto()
    RAT = auto()

class Player:
    """
    Represents a player in the "Rat in the Farm" game.
    """
    def __init__(self, user_id: int, username: str):
        self.user_id: int = user_id
        self.username: str = username
        self.role: Role = Role.FARMER
        self.is_expelled: bool = False
        self.action_taken: bool = False # To track if they've acted this phase
        
    def __repr__(self) -> str:
        return f"Player(id={self.user_id}, username='{self.username}', role={self.role.name})"
