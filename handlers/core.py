import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog
from yunks_game_2_0_1 import database as db
from yunks_game_2_0_1.handlers.decorators import is_admin

logger = structlog.get_logger(__name__)

async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message with a main menu."""
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
        await update.callback_query.message.edit_text(
            text=welcome_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_html(welcome_message, reply_markup=reply_markup)

async def user_profile(update: Update, context: CallbackContext) -> None:
    """Displays the user's profile."""
    user = update.effective_user
    logger.info("user_profile_command", user_id=user.id)
    db_client = context.bot_data['db']
    
    user_data = await db.get_user_data(db_client, user.id)
    
    if user_data:
        username = user_data.get('username', 'N/A')
        xp = user_data.get('xp', 0)
        profile_text = (
            f"👤 <b>Your Profile</b>\n\n"
            f"✨ <b>Username:</b> @{html.escape(username)}\n"
            f"🌟 <b>XP:</b> {xp}"
        )
    else:
        profile_text = "You don't have a profile yet. Send some messages to start!"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to Main Menu", callback_data='start_menu')]
    ])

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=profile_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_html(profile_text, reply_markup=keyboard)

async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Displays the leaderboard, with an optional limit."""
    logger.info("leaderboard_command", user_id=update.effective_user.id)
    db_client = context.bot_data['db']
    limit = 10

    if context.args:
        try:
            requested_limit = int(context.args[0])
            if 1 <= requested_limit <= 100:
                limit = requested_limit
            else:
                if update.message:
                    await update.message.reply_text("Please provide a number between 1 and 100.")
                return
        except (IndexError, ValueError):
            if update.message:
                await update.message.reply_text("Usage: /leaderboard [number]. Please provide a valid number.")
            return

    leaderboard_data = db.get_leaderboard(db_client, limit=limit)
    
    if not leaderboard_data:
        message_text = "The leaderboard is currently empty."
        if update.callback_query:
            await update.callback_query.message.edit_text(text=message_text)
        else:
            await update.message.reply_text(text=message_text)
        return

    leaderboard_text = f"🏆 <b>Top {limit} Players</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, xp) in enumerate(leaderboard_data):
        place = f"{medals[i]}" if i < 3 else f"  {i+1}. "
        leaderboard_text += f"{place} @{html.escape(str(username))} - {xp} XP\n"

    keyboard = None
    if update.callback_query:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to Main Menu", callback_data='start_menu')]
        ])
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=leaderboard_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_html(leaderboard_text, reply_markup=keyboard)

async def help_command(update: Update, context: CallbackContext) -> None:
    """Sends a detailed help message."""
    help_text = (
        "📚 <b>Yunks Gamebot Guide</b>\n\n"
        "Here's how to interact with the bot:\n\n"
        "<b>Core Commands:</b>\n"
        "  - /start: Shows the main menu.\n"
        "  - /profile or /menu: Displays your XP and stats.\n"
        "  - /leaderboard [N]: Shows the top players (default is 10).\n\n"
        "<b>Action Commands:</b>\n"
        "  - /give &lt;amount&gt; (reply to user): Give some of your XP to another player.\n"
        "  - /steal (reply to user): Attempt to steal XP from someone else. Be careful, it can backfire!\n\n"
        "<b>Games:</b>\n"
        "  - /start_game: Begins a 'Guess the Number' game.\n"
        "  - /lastman: Starts a 'Last Person Standing' lobby.\n"
        "  - /lmw: Starts a 'Last Message Wins' lobby."
    )
    if update.callback_query:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to Main Menu", callback_data='start_menu')]
        ])
        await update.callback_query.message.edit_text(
            text=help_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_html(help_text)
