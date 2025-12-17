import html
from typing import Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .game_state import Game, GamePhase
from .farm import FarmLocation

def get_game_render(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Returns the appropriate text and keyboard for the current game phase.
    """
    phase_renderers = {
        GamePhase.LOBBY: render_lobby,
        GamePhase.SEARCH: render_search,
        GamePhase.RESULTS: render_results,
        GamePhase.MOVEMENT: render_movement,
        GamePhase.SUSPICION: render_suspicion,
        GamePhase.ACCUSATION: render_accusation,
        GamePhase.FARMERS_WIN: render_farmers_win,
        GamePhase.RAT_WINS: render_rat_wins,
    }
    
    renderer = phase_renderers.get(game.phase, render_error)
    return renderer(game)

def render_error(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    text = "❓ An unknown error occurred."
    keyboard = [[InlineKeyboardButton("Reset Game", callback_data="ratgame_reset")]]
    return text, InlineKeyboardMarkup(keyboard)

# --- Phase Renderers ---

def render_lobby(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    player_list = "\n".join([f" - @{html.escape(p.username)}" for p in game.players.values()])
    text = (
        "🌾 <b>RAT IN THE FARM</b> 🐀\n\n"
        "A game of search, sabotage, and suspicion.\n\n"
        f"<b>Players ({len(game.players)}/{game.max_players}):</b>\n"
        f"{player_list}\n\n"
        f"The game owner (@{html.escape(game.players[game.owner_id].username)}) can start the game once there are at least {game.min_players} players."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("➕ Join Game", callback_data="ratgame_join"),
            InlineKeyboardButton("🚪 Leave Game", callback_data="ratgame_leave"),
        ],
        [InlineKeyboardButton("▶️ Start Game", callback_data="ratgame_start_game")],
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def render_search(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        f"🔥 <b>FARM DAMAGE: {game.farm.damage_meter}%</b>\n\n"
        "🔍 <b>SEARCH PHASE</b>\n"
        "Choose a location to search for clues. The Rat secretly chooses where to move next.\n\n"
        "🤔 Click 'Reveal My Role' to privately see your assigned role." # Added hint for role reveal
    )
    
    # Existing keyboard for farm locations
    keyboard_rows = [
        [InlineKeyboardButton(loc.value, callback_data=f"ratgame_action_{loc.name}") for loc in game.farm.locations.keys()]
    ]
    
    # Add role reveal buttons
    role_reveal_buttons = []
    for player_id, player_obj in game.players.items():
        role_reveal_buttons.append(InlineKeyboardButton(f"Reveal Role ({player_obj.username})", callback_data=f"ratgame_reveal_role_{player_id}"))

    # Arrange role reveal buttons into rows of 2
    arranged_role_buttons = [role_reveal_buttons[i:i + 2] for i in range(0, len(role_reveal_buttons), 2)]
    keyboard_rows.extend(arranged_role_buttons)
    
    return text, InlineKeyboardMarkup(keyboard_rows)

def render_results(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    results_text = "\n".join(game.search_results.values())
    text = (
        f"🔥 <b>FARM DAMAGE: {game.farm.damage_meter}%</b>\n\n"
        f"📍 <b>SEARCH RESULTS (Round {game.round_number})</b>\n"
        f"{results_text}"
    )

    keyboard = [[InlineKeyboardButton("🤔 Proceed to Suspicion", callback_data="ratgame_proceed_suspicion")]]
    
    return text, InlineKeyboardMarkup(keyboard)

def render_movement(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    """This phase is functionally identical to the SEARCH phase for the UI."""
    text = (
        f"🔥 <b>FARM DAMAGE: {game.farm.damage_meter}%</b>\n\n"
        "🐀 <b>MOVEMENT PHASE</b>\n"
        "The Rat is choosing where to move. Farmers' actions have no effect."
    )
    
    keyboard = [
        [InlineKeyboardButton(loc.value, callback_data=f"ratgame_action_{loc.name}") for loc in game.farm.locations.keys()]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def render_suspicion(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        f"🔥 <b>FARM DAMAGE: {game.farm.damage_meter}%</b>\n\n"
        "🤔 <b>SUSPICION PHASE</b>\n"
        "Do you want to accuse a player or move to the next round?"
    )

    keyboard = [
        [
            InlineKeyboardButton("🗳 Accuse a Player", callback_data="ratgame_start_accusation"),
            InlineKeyboardButton("⏭ Search Again", callback_data="ratgame_next_round"),
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)

def render_accusation(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    text = "🗳 <b>ACCUSATION</b>\nSelect a player to expel from the farm."
    
    # Create rows of 2 players each
    players = [p for p in game.players.values() if not p.is_expelled]
    player_buttons = [
        InlineKeyboardButton(f"@{html.escape(p.username)}", callback_data=f"ratgame_accuse_{p.user_id}") for p in players
    ]
    
    keyboard = [player_buttons[i:i + 2] for i in range(0, len(player_buttons), 2)]
    keyboard.append([InlineKeyboardButton("🔙 Cancel Accusation", callback_data="ratgame_cancel_accusation")])
    
    return text, InlineKeyboardMarkup(keyboard)

def render_farmers_win(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    text = "🎉 <b>FARMERS WIN!</b> 🎉\nThe Rat has been caught and the farm is safe."
    keyboard = [[InlineKeyboardButton("Play Again", callback_data="ratgame_new_lobby")]]
    return text, InlineKeyboardMarkup(keyboard)

def render_rat_wins(game: Game) -> Tuple[str, InlineKeyboardMarkup]:
    rat_player = game.get_player(game.rat_id)
    text = f"🐀 <b>THE RAT WINS!</b> 🐀\n\n@{html.escape(rat_player.username)} was the Rat! The farm has been overrun."
    keyboard = [[InlineKeyboardButton("Play Again", callback_data="ratgame_new_lobby")]]
    return text, InlineKeyboardMarkup(keyboard)
