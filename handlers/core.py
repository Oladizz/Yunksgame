from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog
import os
import html # Added for HTML escaping
import json # Added for JSON serialization

from Yunks_game.game_logic import interface
from Yunks_game.game_logic.game_state import Game
from Yunks_game.game_logic.player import Player
from Yunks_game.handlers.game_handler import strict_edit_message

logger = structlog.get_logger(__name__)

async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message with a menu and instructions."""
    user = update.effective_user
    logger.info("start_command", user_id=user.id, from_callback=update.callback_query is not None)
    
    keyboard = [
        [InlineKeyboardButton("My Profile", callback_data='profile')],
        [InlineKeyboardButton("Leaderboard", callback_data='leaderboard')],
        [InlineKeyboardButton("Play a Game", callback_data='game_menu')],
        [InlineKeyboardButton("How to Play", callback_data='help_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = (
        rf'🎉 Welcome, {user.mention_html()} to Yunks game! 🎉'
        '\n\n'
        'Use the menu below to navigate your profile, check the leaderboard, or play a game.'
    )

    if update.callback_query:
        # If it's a callback query (from a button), edit the message
        await strict_edit_message(context, update.callback_query.message.chat_id, update.callback_query.message.message_id, welcome_message, reply_markup, parse_mode='HTML')
    else:
        # If it's a command, send a new message
        await update.message.reply_html(welcome_message, reply_markup=reply_markup)

async def help_command(update: Update, context: CallbackContext) -> None:
    """Sends a detailed help message."""
    help_text = (
        "📚 <b>Yunks Gamebot Guide</b>\n\n"
        "Welcome! Here's how to interact with the bot:\n\n"
        "✨ <b>Earning XP (Experience Points)</b>:\n"
        "  - Simply send messages in any group where the bot is present. Each message contributes to your XP!\n"
        "  - Win games to earn significant bonus XP!\n\n"
        "🏆 <b>Commands & Features</b>:\n"
        "  - /start: Get a welcome message and the main menu buttons.\n"
        "    <i>Example:</i> `/start`\n\n"
        "  - /help: Access this detailed guide to all bot commands and features.\n"
        "    <i>Example:</i> `/help`\n\n"
        "  - /start_game: Start a 'Guess the Number' game. Guess a number between 1 and 100 within 7 tries.\n"
        "    <i>Example:</i> `/start_game`\n\n"
        "  - /farm: Start a 'Rat in the Farm' game lobby. Players can join, and roles (Rat or Farmer) are assigned secretly.\n"
        "    <i>Example:</i> `/farm`\n\n"
        "  - /lastman: Start a 'Last Person Standing' game. Players are eliminated one by one until only three winners remain.\n"
        "    <i>Example:</i> `/lastman`\n\n"
        "  - /lmw: Start a 'Last Message Wins' game. The last person to send a message before the timer ends wins the XP pool!\n"
        "    <i>Example:</i> `/lmw`\n\n"
        "  - /steal &lt;reply_to_user&gt;: Attempt to steal XP from another user by replying to their message. Be careful, you might lose XP!\n"
        "    <i>Example:</i> `/steal` (reply to a user's message)\n\n"
        "  - /give &lt;amount&gt; &lt;reply_to_user&gt;: Generously give a specified amount of your XP to another user by replying to their message.\n"
        "    <i>Example:</i> `/give 50` (reply to a user's message)\n\n"
        "  - /awardxp &lt;amount&gt; &lt;reply_to_user&gt;: (Admin Only) Award a specified amount of XP to a user. Reply to the user's message.\n"
        "    <i>Example:</i> `/awardxp 100` (reply to a user's message)\n\n"
        "  - /endgame: End any active 'Rat in the Farm' or 'Guess the Number' game in the current chat.\n"
        "    <i>Example:</i> `/endgame`\n\n"
        "  - **Mentioning the bot:** If you mention the bot's username in a message, it will introduce itself and tell you how to start.\n"
        "    <i>Example:</i> `@YunksGameBot hello`\n\n"
        "Enjoy your gamified experience! If you have questions, feel free to ask!"
    )
    if update.message:
        await update.message.reply_html(help_text)
    elif update.callback_query:
        await strict_edit_message(context, update.callback_query.message.chat_id, update.callback_query.message.message_id, help_text, None, parse_mode='HTML')

async def start_farm_game(update: Update, context: CallbackContext) -> None:
    """Starts a new 'Rat in the Farm' game lobby."""
    # This function can be called by a command (Update) or a button (CallbackQuery)
    if update.callback_query:
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
        reply_target = update.callback_query.message
    else:
        user = update.effective_user
        chat_id = update.effective_chat.id
        reply_target = update.message

    # --- Restrict game start to a specific user for testing ---
    allowed_user_id = os.getenv("GAME_HOST_USER_ID")
    if allowed_user_id and str(user.id) != allowed_user_id:
        await reply_target.reply_text("Only the designated test user can start the game for now.")
        return
    # --- End restriction ---

    if 'rat_game' in context.chat_data:
        await reply_target.reply_text("A game is already in progress in this chat!")
        return

    logger.info("Starting new farm game lobby", chat_id=chat_id, user_id=user.id)
    
    # Create a new game instance and add the creator
    game = Game(chat_id=chat_id, owner_id=user.id)
    game.add_player(Player(user.id, user.username or f"user{user.id}"))
    
    context.chat_data['rat_game'] = game

    # Render and send the lobby message
    text, keyboard = interface.get_game_render(game)
    message = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='HTML')    
    # Initialize strict_edit_message cache for the newly sent message
    cache_key = f"msg_cache_{chat_id}_{message.message_id}"
    context.chat_data[cache_key] = {
        'text': text,
        'markup': json.dumps(keyboard.to_dict()) # Store JSON string
    }
    # Save the message ID to the game state so we can edit it later
    game.game_message_id = message.message_id
