from enum import Enum, auto
from typing import Dict, Optional
import random

class FarmLocation(Enum):
    """Represents the different searchable locations on the farm."""
    BARN = "🏚 Barn"
    CORNFIELD = "🌽 Cornfield"
    STORAGE_SHED = "🚜 Storage Shed"
    WATER_AREA = "🌊 Water Area"
    CHICKEN_COOP = "🐓 Chicken Coop"

class Farm:
    """
    Manages the state of the farm, including locations, rat's position,
    and damage.
    """
    def __init__(self, locations: list[FarmLocation]):
        self.locations = {loc: {"searched_by": set(), "clue_found": False} for loc in locations}
        self.rat_location: Optional[FarmLocation] = random.choice(locations)
        self.damage_meter: int = 0
        self.max_damage: int = 100

    def add_damage(self, amount: int):
        """Adds damage to the farm, up to the maximum."""
        self.damage_meter = min(self.damage_meter + amount, self.max_damage)

    def is_destroyed(self) -> bool:
        """Checks if the farm has been destroyed."""
        return self.damage_meter >= self.max_damage

    def reset_round(self):
        """Resets the search state for each location for the new round."""
        for loc in self.locations:
            self.locations[loc]["searched_by"] = set()
            self.locations[loc]["clue_found"] = False
            
    def move_rat(self, new_location: FarmLocation):
        """Moves the rat to a new, different location."""
        # Ensure the rat actually moves to a new spot
        possible_locations = [loc for loc in self.locations if loc != self.rat_location]
        if new_location in possible_locations:
            self.rat_location = new_location
        else: # If rat tries to stay or picks an invalid spot, move it randomly
            self.rat_location = random.choice(possible_locations)
            
    def process_searches(self) -> Dict[FarmLocation, str]:
        """
        Processes the searches for the round and determines where clues are found.
        Returns a dictionary of locations and the result string.
        """
        results = {}
        for loc, state in self.locations.items():
            is_rat_here = (loc == self.rat_location)
            is_searched = len(state["searched_by"]) > 0
            
            # Simplified probability logic for now
            # High chance of clue if Rat is here and it's searched
            if is_searched and is_rat_here:
                if random.random() < 0.85: # 85% chance
                    state["clue_found"] = True
            # Low chance of clue if Rat is not here but it's searched
            elif is_searched and not is_rat_here:
                if random.random() < 0.15: # 15% chance of a false positive
                    state["clue_found"] = True
            
            # Determine result string
            if state["clue_found"]:
                results[loc] = f"{loc.value} → Scratch marks found"
            else:
                results[loc] = f"{loc.value} → Nothing to report"
        
        # If the rat's location was NOT searched, add damage
        if not self.locations[self.rat_location]["searched_by"]:
            self.add_damage(15)
            
        return results
