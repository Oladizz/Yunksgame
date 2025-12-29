import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import structlog
from .. import database as db

logger = structlog.get_logger(__name__)

GAME_DURATION = 60  # seconds for testing, can be increased
ELIMINATION_INTERVAL = 10 # seconds
WINNERS_COUNT = 3
XP_AWARD_WINNER = 10
XP_AWARD_TOP_3 = 5

async def start_lastman_lobby(update: Update, context: CallbackContext) -> None:
    """Starts a lobby for the 'Last Person Standing' game."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    if 'lastman_game' not in context.chat_data:
        context.chat_data['lastman_game'] = {
            'status': 'lobby',
            'players': {},
            'message_id': None,
            'job': None
        }
        
    game_data = context.chat_data['lastman_game']

    if game_data['status'] != 'lobby':
        if update.callback_query:
            await update.callback_query.answer("A 'Last Person Standing' game is already in progress!", show_alert=True)
        else:
            await update.message.reply_text("A 'Last Person Standing' game is already in progress!")
        return
    
    if user.id in game_data['players']:
        if update.callback_query:
            await update.callback_query.answer("You are already in the lobby!", show_alert=True)
        else:
            await update.message.reply_text("You are already in the lobby!")
        return

    game_data['players'][user.id] = {
        'username': user.username if user.username else user.first_name,
        'mention': user.mention_html()
    }

    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data='lastman_join')],
        [InlineKeyboardButton("Start Game", callback_data='lastman_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if not game_data['message_id']:
        reply_method = update.message.reply_html if update.message else update.callback_query.message.reply_html
        message = await reply_method(
            f"👑 <b>Last Person Standing Lobby</b> 👑\n\n"
            f"Current players: {len(game_data['players'])}\n"
            f"Join to compete! Last three standing win XP!\n\n"
            f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}",
            reply_markup=reply_markup
        )
        game_data['message_id'] = message.message_id
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_data['message_id'],
            text=f"👑 <b>Last Person Standing Lobby</b> 👑\n\n"
                 f"Current players: {len(game_data['players'])}\n"
                 f"Join to compete! Last three standing win XP!\n\n"
                 f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    logger.info("Last Man Standing lobby updated", chat_id=chat_id, players=game_data['players'])

async def lastman_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handles callbacks for the 'Last Person Standing' game."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = query.from_user

    if 'lastman_game' not in context.chat_data:
        await query.edit_message_text("No active 'Last Person Standing' game lobby.")
        return
    
    game_data = context.chat_data['lastman_game']

    if query.data == 'lastman_join':
        if game_data['status'] != 'lobby':
            await query.answer("Game already started!", show_alert=True)
            return
        if user.id in game_data['players']:
            await query.answer("You are already in the lobby!", show_alert=True)
            return
        
        game_data['players'][user.id] = {
            'username': user.username if user.username else user.first_name,
            'mention': user.mention_html()
        }
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text=f"👑 <b>Last Person Standing Lobby</b> 👑\n\n"
                 f"Current players: {len(game_data['players'])}\n"
                 f"Join to compete! Last three standing win XP!\n\n"
                 f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}",
            reply_markup=query.message.reply_markup,
            parse_mode='HTML'
        )
        logger.info("Player joined Last Man Standing lobby", chat_id=chat_id, user_id=user.id)

    elif query.data == 'lastman_start':
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
            text=f"👑 <b>Last Person Standing Game Started!</b> 👑\n\n"
                 f"Players: {', '.join([p['username'] for p in game_data['players'].values()])}\n\n"
                 f"Get ready for eliminations!",
            parse_mode='HTML',
            reply_markup=None # Remove buttons
        )
        logger.info("Last Man Standing game started", chat_id=chat_id, players=game_data['players'])
        await start_elimination_phase(update, context)

async def start_elimination_phase(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    game_data = context.chat_data['lastman_game']

    players_remaining = list(game_data['players'].keys())
    random.shuffle(players_remaining) # Shuffle to randomize initial elimination order

    game_data['players_remaining'] = players_remaining
    game_data['eliminated_players'] = []
    game_data['round'] = 0

    await notify_next_elimination(context, chat_id)

async def notify_next_elimination(context: CallbackContext, chat_id: int) -> None:
    game_data = context.chat_data['lastman_game']
    
    if len(game_data['players_remaining']) <= WINNERS_COUNT:
        await end_lastman_game(context, chat_id)
        return

    game_data['round'] += 1
    current_round = game_data['round']

    next_elimination_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚨 <b>Round {current_round}: Elimination in {ELIMINATION_INTERVAL} seconds!</b> 🚨\n\n"
             f"Players remaining: {len(game_data['players_remaining'])}",
        parse_mode='HTML'
    )
    game_data['last_message'] = next_elimination_message.message_id

    # Schedule the elimination
    context.job_queue.run_once(
        perform_elimination,
        ELIMINATION_INTERVAL,
        data={'chat_id': chat_id},
        chat_id=chat_id,
        name=f"lastman_elimination_{chat_id}"
    )

async def perform_elimination(context: CallbackContext) -> None:
    chat_id = context.job.data['chat_id']
    game_data = context.chat_data['lastman_game']

    if len(game_data['players_remaining']) <= WINNERS_COUNT:
        await end_lastman_game(context, chat_id)
        return

    eliminated_user_id = game_data['players_remaining'].pop(0) # FIFO elimination order
    eliminated_player_info = game_data['players'][eliminated_user_id]
    game_data['eliminated_players'].append(eliminated_player_info)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"💀 {eliminated_player_info['mention']} has been eliminated!",
        parse_mode='HTML'
    )
    logger.info("Player eliminated in Last Man Standing", chat_id=chat_id, user_id=eliminated_user_id)

    # Schedule next elimination or end game if enough winners
    if len(game_data['players_remaining']) > WINNERS_COUNT:
        await notify_next_elimination(context, chat_id)
    else:
        await end_lastman_game(context, chat_id)

async def end_lastman_game(context: CallbackContext, chat_id: int) -> None:
    game_data = context.chat_data['lastman_game']
    game_data['status'] = 'finished'
    
    # Announce winners
    winners = []
    for user_id in game_data['players_remaining']:
        winners.append(game_data['players'][user_id]['mention'])
        await db.add_xp(context.bot_data['db'], user_id, game_data['players'][user_id]['username'], XP_AWARD_TOP_3)

    if winners:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏆 <b>Game Over! The last players standing are:</b> {', '.join(winners)}!\n\n"
                 f"They each earned {XP_AWARD_TOP_3} XP!",
            parse_mode='HTML'
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Game Over! No winners this round."
        )

    logger.info("Last Man Standing game ended", chat_id=chat_id, winners=winners)
    # Clean up game data
    del context.chat_data['lastman_game']
