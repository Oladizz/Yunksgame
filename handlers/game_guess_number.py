import random
import structlog
from telegram import Update
from telegram.ext import CallbackContext
from .. import database as db
from .decorators import is_admin

logger = structlog.get_logger(__name__)

@is_admin
async def start_new_game(update: Update, context: CallbackContext):
    """Starts a new 'Guess the Number' game."""
    user = update.effective_user
    user_id = user.id
    secret_number = random.randint(1, 100)
    max_tries = 7
    
    context.user_data['game'] = {
        'secret_number': secret_number,
        'tries_left': max_tries
    }
    
    logger.info("New game started", user_id=user_id, secret_number=secret_number, max_tries=max_tries)
    
    message_text = (
        f"🎲 I'm thinking of a number between 1 and 100. "
        f"You have {max_tries} tries to guess it! What's your first guess?"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(message_text)
    else:
        await update.message.reply_text(message_text)

async def handle_guess(update: Update, context: CallbackContext):
    """Handles a user's guess in the 'Guess the Number' game."""
    user = update.effective_user
    
    if 'game' not in context.user_data:
        await update.message.reply_text("You don't have an active game. Use /start_game to begin!")
        return

    try:
        user_guess = int(update.message.text)
    except (ValueError, TypeError):
        await update.message.reply_text("That's not a valid number. Please guess a whole number.")
        return

    game_state = context.user_data['game']
    secret_number = game_state['secret_number']
    tries_left = game_state['tries_left'] - 1
    
    context.user_data['game']['tries_left'] = tries_left

    logger.info("User made a guess", user_id=user.id, guess=user_guess, secret_number=secret_number, tries_left=tries_left)

    if user_guess == secret_number:
        base_xp = 1
        bonus_xp = tries_left 
        xp_award = min(base_xp + bonus_xp, 3) 
        db_client = context.bot_data['db']
        await db.add_xp(db_client, user.id, user.username, xp_to_add=xp_award)
        message = (
            f"🎉 Congratulations! You guessed the number {secret_number} in {7 - tries_left} tries! "
            f"You've earned {xp_award} XP!\n\n"
            "Use /start_game to play again."
        )
        await update.message.reply_text(message)
        del context.user_data['game']
        logger.info("Game won", user_id=user.id, xp_awarded=xp_award)
    elif tries_left <= 0:
        message = (
            f"😔 Oh no! You ran out of tries. The secret number was {secret_number}.\n\n"
            "Use /start_game to play again."
        )
        await update.message.reply_text(message)
        del context.user_data['game']
        logger.info("Game lost", user_id=user.id, secret_number=secret_number)
    elif user_guess < secret_number:
        await update.message.reply_text(f"Too low! You have {tries_left} tries left.")
    else: # user_guess > secret_number
        await update.message.reply_text(f"Too high! You have {tries_left} tries left.")
