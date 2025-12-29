import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog

from yunks_game_2_0_1 import database as db

logger = structlog.get_logger(__name__)

LMW_GAME_DURATION = 30  # seconds for the countdown
LMW_ENTRY_COST = 5
LMW_XP_POT_MULTIPLIER = 0.5  # Each player adds 50% of their entry cost to the pot

async def start_lmw_lobby(update: Update, context: CallbackContext) -> None:
    """Starts a lobby for the 'Last Message Wins' game."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    # --- Pre-check Section ---
    if 'lmw_game' in context.chat_data:
        game_data = context.chat_data['lmw_game']
        if game_data['status'] != 'lobby':
            if update.callback_query:
                await update.callback_query.answer("A 'Last Message Wins' game is already in progress!", show_alert=True)
            else:
                await update.message.reply_text("A 'Last Message Wins' game is already in progress!")
            return
        if user.id in game_data['players']:
            if update.callback_query:
                await update.callback_query.answer("You are already in the lobby!", show_alert=True)
            else:
                await update.message.reply_text("You are already in the lobby!")
            return

    db_client = context.bot_data['db']
    user_data = await db.get_user_data(db_client, user.id)
    if not user_data or user_data.get('xp', 0) < LMW_ENTRY_COST:
        if update.callback_query:
            await update.callback_query.answer(f"You need at least {LMW_ENTRY_COST} XP to join this game!", show_alert=True)
        else:
            await update.message.reply_text(f"You need at least {LMW_ENTRY_COST} XP to join this game!")
        return

    # --- Initialization Section (only if all checks pass) ---
    if 'lmw_game' not in context.chat_data:
        context.chat_data['lmw_game'] = {
            'status': 'lobby',
            'players': {},
            'message_id': None,
            'xp_pot': 0,
            'job': None,
            'last_message_info': {'user_id': None, 'username': None, 'message_id': None, 'timestamp': None}
        }
    
    game_data = context.chat_data['lmw_game']
    
    # Deduct entry cost and add to pot
    await db.add_xp(db_client, user.id, user.username, -LMW_ENTRY_COST)
    game_data['xp_pot'] += int(LMW_ENTRY_COST * LMW_XP_POT_MULTIPLIER)

    game_data['players'][user.id] = {
        'username': user.username if user.username else user.first_name,
        'mention': user.mention_html(),
        'has_messaged': False # Track if player has sent their one message
    }

    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data='lmw_join')],
        [InlineKeyboardButton("Start Game", callback_data='lmw_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    player_list_html = ', '.join([p['mention'] for p in game_data['players'].values()])

    lobby_text = (
        f"👑 <b>Last Message Wins Lobby</b> 👑\n\n"
        f"Entry Cost: {LMW_ENTRY_COST} XP\n"
        f"Current XP Pot: {game_data['xp_pot']} XP\n"
        f"Current players: {len(game_data['players'])}\n"
        f"Join to compete! Last person to send a message wins the pot!\n\n"
        f"Players: {player_list_html}"
    )

    if not game_data['message_id']:
        reply_method = update.message.reply_html if update.message else update.callback_query.message.reply_html
        message = await reply_method(
            lobby_text,
            reply_markup=reply_markup
        )
        game_data['message_id'] = message.message_id
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_data['message_id'],
            text=lobby_text,
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
        if user.id in game_data['players']:
            await query.answer("You are already in the lobby!", show_alert=True)
            return
        
        db_client = context.bot_data['db']
        user_data = await db.get_user_data(db_client, user.id)
        if not user_data or user_data.get('xp', 0) < LMW_ENTRY_COST:
            await query.answer(f"You need at least {LMW_ENTRY_COST} XP to join this game!", show_alert=True)
            return

        await db.add_xp(db_client, user.id, user.username, -LMW_ENTRY_COST)
        game_data['xp_pot'] += int(LMW_ENTRY_COST * LMW_XP_POT_MULTIPLIER)

        game_data['players'][user.id] = {
            'username': user.username if user.username else user.first_name,
            'mention': user.mention_html(),
            'has_messaged': False
        }

        player_list_html = ', '.join([p['mention'] for p in game_data['players'].values()])

        lobby_text = (
            f"👑 <b>Last Message Wins Lobby</b> 👑\n\n"
            f"Entry Cost: {LMW_ENTRY_COST} XP\n"
            f"Current XP Pot: {game_data['xp_pot']} XP\n"
            f"Current players: {len(game_data['players'])}\n"
            f"Join to compete! Last person to send a message wins the pot!\n\n"
            f"Players: {player_list_html}"
        )
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text=lobby_text,
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
        player_list_html = ', '.join([p['mention'] for p in game_data['players'].values()])
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_data['message_id'],
            text=f"👑 <b>Last Message Wins Game Started!</b> 👑\n\n"
                 f"Players: {player_list_html}\n\n"
                 f"The last person to send a message before the timer runs out wins {game_data['xp_pot']} XP!\n"
                 f"You can only send ONE message.",
            parse_mode='HTML',
            reply_markup=None # Remove buttons
        )
        logger.info("LMW game started", chat_id=chat_id, players=game_data['players'])
        await start_lmw_game(update, context)

async def lmw_message_handler(update: Update, context: CallbackContext) -> None:
    """Handles messages during the 'Last Message Wins' game."""
    user = update.effective_user
    
    if 'lmw_game' not in context.chat_data or context.chat_data['lmw_game']['status'] != 'in_progress':
        return # Not in an active LMW game

    game_data = context.chat_data['lmw_game']

    if user.id not in game_data['players']:
        # This message is from someone not in the game
        return

    if game_data['players'][user.id]['has_messaged']:
        try:
            await update.message.reply_text("You have already sent your message for this round!")
        except Exception as e:
            logger.warning("Could not reply to user, probably because message was deleted.", error=e)
        return

    # Record the last message
    game_data['last_message_info'] = {
        'user_id': user.id,
        'username': user.username if user.username else user.first_name,
        'message_id': update.message.message_id,
        'timestamp': time.time()
    }
    game_data['players'][user.id]['has_messaged'] = True
    logger.info("LMW message recorded", chat_id=update.effective_chat.id, user_id=user.id)


async def start_lmw_game(update: Update, context: CallbackContext) -> None:
    """Manages the countdown and determines the winner for 'Last Message Wins'."""
    chat_id = update.effective_chat.id
    game_data = context.chat_data['lmw_game']

    countdown_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ The clock is ticking! You have {LMW_GAME_DURATION} seconds to send your ONE message! Go!",
        parse_mode='HTML'
    )

    # Schedule the end of the game
    game_data['job'] = context.job_queue.run_once(
        end_lmw_game,
        LMW_GAME_DURATION,
        data={'chat_id': chat_id, 'countdown_message_id': countdown_message.message_id},
        chat_id=chat_id,
        name=f"lmw_end_game_{chat_id}"
    )


async def end_lmw_game(context: CallbackContext) -> None:
    """Ends the 'Last Message Wins' game and declares the winner."""
    chat_id = context.job.data['chat_id']
    countdown_message_id = context.job.data['countdown_message_id']
    game_data = context.chat_data['lmw_game']
    game_data['status'] = 'finished'

    winner_info = game_data['last_message_info']
    xp_pot = game_data['xp_pot']

    if winner_info['user_id']:
        db_client = context.bot_data['db']
        await db.add_xp(db_client, winner_info['user_id'], winner_info['username'], xp_pot)
        winner_mention = (await context.bot.get_chat_member(chat_id, winner_info['user_id'])).user.mention_html()
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Time's up! The winner is {winner_mention} with the last message!\n\n"
                 f"They win the entire pot of {xp_pot} XP!",
            parse_mode='HTML',
            reply_to_message_id=winner_info['message_id']
        )
        logger.info("LMW game ended, winner found", chat_id=chat_id, winner_id=winner_info['user_id'], xp_won=xp_pot)
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=countdown_message_id,
            text="😔 Time's up! No one sent a message. The XP pot has been lost to the void...",
            parse_mode='HTML'
        )
        logger.info("LMW game ended, no winner", chat_id=chat_id)

    # Clean up game data
    if 'lmw_game' in context.chat_data:
        del context.chat_data['lmw_game']
