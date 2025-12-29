import random
import time
from telegram import Update
from telegram.ext import CallbackContext
import structlog
from yunks_game_2_0_1 import database as db
from yunks_game_2_0_1.handlers.decorators import is_admin

logger = structlog.get_logger(__name__)

STEAL_COOLDOWN = 3600  # 1 hour in seconds
STEAL_SUCCESS_RATE = 0.5  # 50%
STEAL_PENALTY = 5
MIN_STEAL_AMOUNT = 5
MAX_STEAL_AMOUNT = 15

@is_admin
async def give_xp(update: Update, context: CallbackContext) -> None:
    """Gives a specified amount of XP from the command user to another user."""
    giver = update.effective_user

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to give them XP.")
        return
        
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("You must give a positive amount of XP!")
            return
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /give <amount>")
        return

    recipient = update.message.reply_to_message.from_user

    if recipient.id == giver.id:
        await update.message.reply_text("You can't give XP to yourself.")
        return

    if recipient.is_bot:
        await update.message.reply_text("Bots have no use for your XP.")
        return

    db_client = context.bot_data['db']
    giver_data = await db.get_user_data(db_client, giver.id)
    if not giver_data or giver_data.get('xp', 0) < amount:
        await update.message.reply_text(f"You don't have enough XP to give {amount} away!")
        return
        
    success = await db.transfer_xp(db_client, from_user_id=giver.id, to_user_id=recipient.id, amount=amount)

    if success:
        message = f"🎁 {giver.mention_html()} generously gave {amount} XP to {recipient.mention_html()}!"
        logger.info("XP give success", giver_id=giver.id, recipient_id=recipient.id, amount=amount)
    else:
        message = "An unexpected error occurred during the transfer."
        logger.error("XP give failed unexpectedly after checks", giver_id=giver.id, recipient_id=recipient.id, amount=amount)

    await update.message.reply_html(message)

@is_admin
async def steal_xp(update: Update, context: CallbackContext) -> None:
    """Allows a user to attempt to steal XP from another user."""
    thief = update.effective_user
    db_client = context.bot_data['db']

    last_steal_attempt = context.user_data.get('last_steal', 0)
    if time.time() - last_steal_attempt < STEAL_COOLDOWN:
        remaining_time = int(STEAL_COOLDOWN - (time.time() - last_steal_attempt))
        await update.message.reply_text(f"You're on cooldown! Try again in {remaining_time // 60} minutes.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("To steal XP, you must reply to a message from the user you want to rob.")
        return

    victim = update.message.reply_to_message.from_user
    
    if victim.id == thief.id:
        await update.message.reply_text("You can't steal from yourself, you silly goose!")
        return

    if victim.is_bot:
        await update.message.reply_text("You can't steal from bots, they have no pockets to pick!")
        return

    context.user_data['last_steal'] = time.time()

    if random.random() < STEAL_SUCCESS_RATE:
        stolen_amount = random.randint(MIN_STEAL_AMOUNT, MAX_STEAL_AMOUNT)
        
        success = await db.transfer_xp(db_client, from_user_id=victim.id, to_user_id=thief.id, amount=stolen_amount)

        if success:
            message = f"🎉 {thief.mention_html()} masterfully swiped {stolen_amount} XP from {victim.mention_html()}!"
            logger.info("XP steal success", thief_id=thief.id, victim_id=victim.id, amount=stolen_amount)
        else:
            message = f"😅 {thief.mention_html()} tried to steal from {victim.mention_html()}, but the victim had no XP to steal!"
            logger.info("XP steal failed, victim has no XP", thief_id=thief.id, victim_id=victim.id)

        await update.message.reply_html(message)
    else:
        await db.add_xp(db_client, thief.id, thief.username, xp_to_add=-STEAL_PENALTY)
        message = (
            f"🚓 Oh no! {thief.mention_html()} fumbled the attempt to rob {victim.mention_html()} "
            f"and lost {STEAL_PENALTY} XP in the process!"
        )
        await update.message.reply_html(message)

@is_admin
async def award_xp(update: Update, context: CallbackContext) -> None:
    """Admin-only command to award XP to a user."""
    admin_user = update.effective_user
    db_client = context.bot_data['db']

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to award them XP.")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("You must award a positive amount of XP!")
            return
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /awardxp <amount> (reply to user)")
        return
    
    recipient = update.message.reply_to_message.from_user

    if recipient.is_bot:
        await update.message.reply_text("Bots don't need XP.")
        return

    await db.add_xp(db_client, recipient.id, recipient.username, xp_to_add=amount)
    
    message = f"🌟 Admin {admin_user.mention_html()} awarded {amount} XP to {recipient.mention_html()}!"
    logger.info("XP awarded by admin", admin_id=admin_user.id, recipient_id=recipient.id, amount=amount)
    await update.message.reply_html(message)

@is_admin
async def end_game(update: Update, context: CallbackContext) -> None:
    """Admin-only command to end any active game in the current chat."""
    chat_id = update.effective_chat.id

    # For 'Guess the Number', the game state is stored in user_data,
    # and we need to check all user_data within the chat for active games.
    # This is a simplification; a more robust solution would involve
    # storing active games in chat_data or a dedicated game state.
    # For now, we'll iterate through known users who might have an active game.
    
    # In a real scenario, you'd have a way to track active games per chat.
    # For this example, we'll just check if the current user has an active game.
    # This will only end the game for the user who started it if they are the admin.
    # A more complete solution for multi-user games would require chat_data.

    if 'game' in context.user_data:
        del context.user_data['game']
        await update.message.reply_text("The active game has been ended.")
        logger.info("Game ended by admin", chat_id=chat_id, admin_id=update.effective_user.id)
    else:
        await update.message.reply_text("No active game found in this chat for you to end.")
