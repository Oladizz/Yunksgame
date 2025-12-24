from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext

def is_admin(func):
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        chat = update.effective_chat
        user_id = update.effective_user.id
        
        if chat.type == 'private':
            # In private chats, all users are "admins" of their own chat
            return await func(update, context, *args, **kwargs)

        chat_admins = await context.bot.get_chat_administrators(chat.id)
        is_user_admin = any(admin.user.id == user_id for admin in chat_admins)
        
        if is_user_admin:
            return await func(update, context, *args, **kwargs)
        else:
            if update.message:
                await update.message.reply_text("This command can only be used by group admins.")
            elif update.callback_query:
                await update.callback_query.answer("This command can only be used by group admins.", show_alert=True)
    return wrapped
