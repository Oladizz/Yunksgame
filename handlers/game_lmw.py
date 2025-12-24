import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog
from .. import database as db

logger = structlog.get_logger(__name__)

ENTRY_FEE = 10
COUNTDOWN_SECONDS = 30

async def start_lmw_lobby(update: Update, context: CallbackContext) -> None:
    """Starts a lobby for the 'Last Message Wins' game."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    if 'lmw_game' not in context.chat_data:
        context.chat_data['lmw_game'] = {
            'status': 'lobby',
            'players': {},
            'message_id': None,
            'job': None,
            'xp_pool': 0
        }
        
    game_data = context.chat_data['lmw_game']

    if game_data['status'] != 'lobby':
        if update.callback_query:
            await update.callback_query.answer("A 'Last Message Wins' game is already in progress!", show_alert=True)
        else:
            await update.message.reply_text("A 'Last Message Wins' game is already in progress!")
        return
    
    user_data = await db.get_user_data(context.bot_data['db'], user.id)
    if not user_data or user_data.get('xp', 0) < ENTRY_FEE:
        if update.callback_query:
            await update.callback_query.answer(f"You need at least {ENTRY_FEE} XP to join!", show_alert=True)
        else:
            await update.message.reply_text(f"You need at least {ENTRY_FEE} XP to join!")
        return
        
    if user.id in game_data['players']:
        if update.callback_query:
            await update.callback_query.answer("You are already in the lobby!", show_alert=True)
        else:
            await update.message.reply_text("You are already in the lobby!")
        return

    # Deduct XP and add to pool
    await db.add_xp(context.bot_data['db'], user.id, user.username, xp_to_add=-ENTRY_FEE)
    game_data['xp_pool'] += ENTRY_FEE
    
    game_data['players'][user.id] = {
        'username': user.username if user.username else user.first_name,
        'mention': user.mention_html()
    }

    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data='lmw_join')],
        [InlineKeyboardButton("Start Game", callback_data='lmw_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"🏆 <b>Last Message Wins Lobby</b> 🏆\n\n"
        f"Current players: {len(game_data['players'])}\n"
        f"Entry Fee: {ENTRY_FEE} XP\n"
        f"XP Pool: {game_data['xp_pool']}\n\n"
        f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    elif not game_data['message_id']:
        message = await update.message.reply_html(text, reply_markup=reply_markup)
        game_data['message_id'] = message.message_id
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_data['message_id'],
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    logger.info("LMW lobby updated", chat_id=chat_id, players=game_data['players'])

async def lmw_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handles callbacks for the 'Last Message Wins' game."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = query.from_user

    if 'lmw_game' not in context.chat_data:
        await query.edit_message_text("No active 'Last Message Wins' game lobby.")
        return
    
    game_data = context.chat_data['lmw_game']

    if query.data == 'lmw_join':
        if game_data['status'] != 'lobby':
            await query.answer("Game already started!", show_alert=True)
            return
            
        user_data = await db.get_user_data(context.bot_data['db'], user.id)
        if not user_data or user_data.get('xp', 0) < ENTRY_FEE:
            await query.answer(f"You need at least {ENTRY_FEE} XP to join!", show_alert=True)
            return
            
        if user.id in game_data['players']:
            await query.answer("You are already in the lobby!", show_alert=True)
            return
        
        # Deduct XP and add to pool
        await db.add_xp(context.bot_data['db'], user.id, user.username, xp_to_add=-ENTRY_FEE)
        game_data['xp_pool'] += ENTRY_FEE

        game_data['players'][user.id] = {
            'username': user.username if user.username else user.first_name,
            'mention': user.mention_html()
        }
        
        text = (
            f"🏆 <b>Last Message Wins Lobby</b> 🏆\n\n"
            f"Current players: {len(game_data['players'])}\n"
            f"Entry Fee: {ENTRY_FEE} XP\n"
            f"XP Pool: {game_data['xp_pool']}\n\n"
            f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}"
        )

        await query.message.edit_text(
            text=text,
            reply_markup=query.message.reply_markup,
            parse_mode='HTML'
        )
        logger.info("Player joined LMW lobby", chat_id=chat_id, user_id=user.id)

    elif query.data == 'lmw_start':
        if game_data['status'] != 'lobby':
            await query.answer("Game already started!", show_alert=True)
            return
        if len(game_data['players']) < 2:
            await query.answer("Need at least 2 players to start the game!", show_alert=True)
            return
        
        # Start the game
        game_data['status'] = 'in_progress'
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_data['message_id'],
            text=f"🏆 <b>Last Message Wins Game Started!</b> 🏆\n\n"
                 f"The game will end in {COUNTDOWN_SECONDS} seconds. The last person to send a message wins!",
            parse_mode='HTML',
            reply_markup=None # Remove buttons
        )
        
        # Schedule the end of the game
        context.job_queue.run_once(
            end_lmw_game,
            COUNTDOWN_SECONDS,
            data={'chat_id': chat_id},
            chat_id=chat_id,
            name=f"lmw_end_{chat_id}"
        )
        logger.info("LMW game started", chat_id=chat_id, players=game_data['players'])

async def end_lmw_game(context: CallbackContext) -> None:
    chat_id = context.job.data['chat_id']
    game_data = context.chat_data['lmw_game']
    
    if game_data['status'] != 'in_progress':
        return

    game_data['status'] = 'finished'
    
    winner_id = game_data.get('last_message_user_id')
    
    if winner_id:
        winner_info = game_data['players'][winner_id]
        await db.add_xp(context.bot_data['db'], winner_id, winner_info['username'], game_data['xp_pool'])
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Congratulations {winner_info['mention']}! You won {game_data['xp_pool']} XP!",
            parse_mode='HTML'
        )
    else:
        # Refund XP if no one sent a message
        for user_id, player_info in game_data['players'].items():
            await db.add_xp(context.bot_data['db'], user_id, player_info['username'], ENTRY_FEE)
            
        await context.bot.send_message(chat_id=chat_id, text="No one sent a message. XP has been refunded.")

    logger.info("LMW game ended", chat_id=chat_id, winner_id=winner_id)
    del context.chat_data['lmw_game']

async def handle_lmw_message(update: Update, context: CallbackContext) -> None:
    """Handles messages during the LMW game."""
    user_id = update.effective_user.id
    
    if 'lmw_game' in context.chat_data and context.chat_data['lmw_game']['status'] == 'in_progress':
        game_data = context.chat_data['lmw_game']
        if user_id in game_data['players']:
            game_data['last_message_user_id'] = user_id