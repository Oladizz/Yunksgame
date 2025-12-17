import random
import structlog
from . import database

logger = structlog.get_logger(__name__)

async def start_new_game(update, context):
    """Starts a new 'Guess the Number' game."""
    user_id = update.effective_user.id
    secret_number = random.randint(1, 100)
    max_tries = 7
    
    # Store game state in user_data
    context.user_data['game'] = {
        'secret_number': secret_number,
        'tries_left': max_tries
    }
    
    logger.info("New game started", user_id=user_id, secret_number=secret_number, max_tries=max_tries)
    
    message = (
        "🎲 I'm thinking of a number between 1 and 100. "
        f"You have {max_tries} tries to guess it! What's your first guess?"
    )
    await update.message.reply_text(message)

async def handle_guess(update, context):
    """Handles a user's guess in the 'Guess the Number' game."""
    user_id = update.effective_user.id
    
    if 'game' not in context.user_data:
        logger.warning("No active game for user", user_id=user_id)
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

    logger.info("User made a guess", user_id=user_id, guess=user_guess, secret_number=secret_number, tries_left=tries_left)

    if user_guess == secret_number:
        base_xp = 1
        bonus_xp = tries_left # 1 XP for each try left
        xp_award = min(base_xp + bonus_xp, 3) # Cap XP at a maximum of 3
        db_client = context.bot_data['db']
        database.add_xp(db_client, user_id, update.effective_user.username, xp_to_add=xp_award)
        message = (
            f"🎉 Congratulations! You guessed the number {secret_number} in {7 - tries_left} tries! "
            f"You've earned {xp_award} XP!\n\n"
            "Use /start_game to play again."
        )
        await update.message.reply_text(message)
        del context.user_data['game'] # End the game
        logger.info("Game won", user_id=user_id, xp_awarded=xp_award)
    elif tries_left <= 0:
        message = (
            f"😔 Oh no! You ran out of tries. The secret number was {secret_number}.\n\n"
            "Use /start_game to play again."
        )
        await update.message.reply_text(message)
        del context.user_data['game'] # End the game
        logger.info("Game lost", user_id=user_id, secret_number=secret_number)
    elif user_guess < secret_number:
        await update.message.reply_text(f"Too low! You have {tries_left} tries left.")
    else: # user_guess > secret_number
        await update.message.reply_text(f"Too high! You have {tries_left} tries left.")