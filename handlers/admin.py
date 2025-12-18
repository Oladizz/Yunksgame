import os
from telegram import Update
from telegram.ext import CallbackContext
import structlog
from Yunks_game import database as db

logger = structlog.get_logger(__name__)

# A simple way to manage admins - user IDs from an environment variable
ADMIN_USER_IDS = [int(i) for i in os.getenv("ADMIN_USER_IDS", "").split(',') if i]

async def award_xp(update: Update, context: CallbackContext) -> None:
    """Awards a specified amount of XP to a user. Admin-only."""
    admin = update.effective_user
    
    if admin.id not in ADMIN_USER_IDS:
        await update.message.reply_text("This is an admin-only command.")
        logger.warning("Non-admin user tried to use /awardxp", user_id=admin.id)
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to award them XP.")
        return
        
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /awardxp <amount>")
        return

    target_user = update.message.reply_to_message.from_user
    db_client = context.bot_data['db']
    
    await db.add_xp(db_client, target_user.id, target_user.username, xp_to_add=amount)
    
    await update.message.reply_text(f"Successfully awarded {amount} XP to @{target_user.username}.")
    logger.info("Admin awarded XP", admin_id=admin.id, target_id=target_user.id, amount=amount)

async def end_game_command(update: Update, context: CallbackContext) -> None:
    """Ends any active game in the current chat. Admin-only."""
    admin = update.effective_user

    if admin.id not in ADMIN_USER_IDS:
        await update.message.reply_text("This is an admin-only command.")
        logger.warning("Non-admin user tried to use /endgame", user_id=admin.id)
        return

    chat_id = update.effective_chat.id
    
    if 'rat_game' in context.chat_data and context.chat_data['rat_game'].chat_id == chat_id:
        game = context.chat_data.pop('rat_game')
        await update.message.reply_text("The current game of 'Rat in the Farm' has been ended.")
        logger.info("Game ended by command", chat_id=chat_id, game_id=game.game_message_id)
    else:
        await update.message.reply_text("There is no active game of 'Rat in the Farm' in this chat.")
        logger.info("End game command issued with no active game", chat_id=chat_id)
