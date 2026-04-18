# main.py
import telebot
import logging
import random
import time
import re
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK, TRIGGER_WORD
from database import (get_user, create_user, update_user, add_xp, update_elo, 
                      get_top_by_elo, get_top_by_level, save_message_history)
from games import (play_dice, play_rps, play_slots, calculate_duel_damage, 
                   check_winner, print_board)
from keyboards import (get_main_keyboard, get_games_keyboard, get_duel_bot_keyboard, 
                       get_back_keyboard, create_ttt_keyboard)
from ai_helper import ask_ai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)
bot.skip_pending = True

# Хранилища для игр
duel_bot_games = {}
duel_requests = {}
tictactoe_requests = {}
tictactoe_games = {}

# ========== ПРОВЕРКА ПОДПИСКИ ==========
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def subscription_required(func):
    def wrapper(message):
        if check_subscription(message.from_user.id):
            return func(message)
        else:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=REQUIRED_CHANNEL_LINK))
            bot.send_message(message.chat.id, "🔒 <b>Подпишись на канал!</b>", parse_mode='HTML', reply_markup=markup)
    return wrapper

# ========== ОБРАБОТКА ВСЕХ СООБЩЕНИЙ ==========
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    is_group = message.chat.type in ['group', 'supergroup']
    
    if not text:
        return
    
    # Обновляем счётчик сообщений
    user = get_user(user_id)
    if user:
        update_user(user_id, messages_count=user['messages_count'] + 1)
        add_xp(user_id, 1)
    else:
        user = create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    
    # В группах — отвечаем только на триггерное слово
    if is_group:
        if not re.search(TRIGGER_WORD, text.lower()):
            return
        # Убираем триггер из текста
        clean_text = re.sub(TRIGGER_WORD, '', text, flags=re.IGNORECASE).strip()
        if not clean_text:
            bot.reply_to(message, "Чё хотел?")
            return
        question = clean_text
    else:
        # В ЛС — отвечаем на всё
        question = text
    
    # Показываем "печатает"
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Получаем ответ от ИИ
    reply = ask_ai(question, user_id)
    
    if reply:
        bot.reply_to(message, reply)
    else:
        bot.reply_to(message, "⚠️ Ошибка, попробуй позже")

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
@subscription_required
def start_cmd(message):
    user_id = message.from_user.id
    user = create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    
    text = f"""🎉 <b>ДОБРО ПОЖАЛОВАТЬ!</b> 🎉

Привет, {message.from_user.first_name}!

📌 <b>Твоя статистика:</b>
├ Уровень: {user['level']}
├ Опыт: {user['xp']}/{user['level']*100}
├ Монет: {user['coins']}
├ Побед: {user['wins']}
├ Поражений: {user['losses']}
└ Рейтинг ELO: {user['elo_rating']}

🎮 <b>В чатах:</b> напиши "{TRIGGER_WORD} вопрос" — я отвечу!
💬 <b>В ЛС:</b> просто пиши вопросы

Используй кнопки меню для игр!
"""
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 ПРОФИЛЬ")
@subscription_required
def profile_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    
    text = f"""👤 <b>ПРОФИЛЬ</b>

├ ID: <code>{user['user_id']}</code>
├ Имя: {user['first_name']}
├ Юзернейм: @{user['username'] or 'нет'}
├ Уровень: {user['level']} ({user['xp']}/{user['level']*100} XP)
├ Монет: {user['coins']} 💰
├ Побед: {user['wins']}
├ Поражений: {user['losses']}
├ Ничьих: {user['draws']}
├ Рейтинг ELO: {user['elo_rating']} 🏆
├ Сообщений: {user['messages_count']}
╰ Дата регистрации: {user['registered_date'][:10]}

📅 Ежедневный бонус: /daily
"""
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "💰 ЕЖЕДНЕВНЫЙ БОНУС")
@subscription_required
def daily_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    today = datetime.now().date()
    
    if user['last_daily']:
        last = datetime.fromisoformat(user['last_daily']).date()
        if last == today:
            bot.send_message(message.chat.id, "❌ Ты уже получал бонус сегодня! Завтра приходи.", parse_mode='HTML')
            return
        if last == today - timedelta(days=1):
            streak = user['daily_streak'] + 1
        else:
            streak = 1
    else:
        streak = 1
    
    bonus = 50 + (streak * 10)
    update_user(user_id, coins=user['coins'] + bonus, daily_streak=streak, last_daily=datetime.now().isoformat())
    add_xp(user_id, 20)
    
    text = f"✅ Ежедневный бонус: +{bonus}💰\n🔥 Стрик: {streak} дней"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🏆 РЕЙТИНГ")
@subscription_required
def rating_cmd(message):
    top_elo = get_top_by_elo(10)
    top_level = get_top_by_level(10)
    
    text = "🏆 <b>ТОП ПО РЕЙТИНГУ ELO</b>\n"
    for i, (uid, username, elo) in enumerate(top_elo, 1):
        name = f"@{username}" if username else f"ID{uid}"
        text += f"{i}. {name} — {elo} 🏆\n"
    
    text += "\n🏆 <b>ТОП ПО УРОВНЮ</b>\n"
    for i, (uid, username, lvl, xp) in enumerate(top_level, 1):
        name = f"@{username}" if username else f"ID{uid}"
        text += f"{i}. {name} — {lvl} уровень ({xp} XP)\n"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🎮 ИГРЫ")
@subscription_required
def games_menu_cmd(message):
    bot.send_message(message.chat.id, "🎮 <b>ВЫБЕРИ ИГРУ</b>", parse_mode='HTML', reply_markup=get_games_keyboard())

@bot.message_handler(func=lambda m: m.text == "◀️ НАЗАД")
def back_cmd(message):
    bot.send_message(message.chat.id, "📋 <b>ГЛАВНОЕ МЕНЮ</b>", parse_mode='HTML', reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🎲 КУБИК")
@subscription_required
def game_dice_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    dice = play_dice()
    add_xp(user_id, 2)
    update_user(user_id, coins=user['coins'] + dice)
    bot.send_message(message.chat.id, f"🎲 <b>Твой бросок:</b> {dice}\n💰 +{dice} монет!", parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "✂️ КНБ")
@subscription_required
def game_rps_cmd(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        telebot.types.KeyboardButton("🗻 КАМЕНЬ"),
        telebot.types.KeyboardButton("✂️ НОЖНИЦЫ"),
        telebot.types.KeyboardButton("📄 БУМАГА"),
        telebot.types.KeyboardButton("◀️ НАЗАД")
    )
    bot.send_message(message.chat.id, "✂️ <b>ВЫБЕРИ ФИГУРУ</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["🗻 КАМЕНЬ", "✂️ НОЖНИЦЫ", "📄 БУМАГА"])
@subscription_required
def game_rps_play_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    choices = {"🗻 КАМЕНЬ": "камень", "✂️ НОЖНИЦЫ": "ножницы", "📄 БУМАГА": "бумага"}
    user_choice = choices[message.text]
    bot_choice, result, delta = play_rps(user_choice)
    
    if result == 'win':
        update_user(user_id, wins=user['wins'] + 1, coins=user['coins'] + delta)
        add_xp(user_id, 10)
        text = f"🤖 Бот: {bot_choice}\n✅ <b>ПОБЕДА!</b> +{delta}💰"
    elif result == 'lose':
        update_user(user_id, losses=user['losses'] + 1, coins=user['coins'] + delta)
        text = f"🤖 Бот: {bot_choice}\n❌ <b>ПОРАЖЕНИЕ</b> {abs(delta)}💰"
    else:
        text = f"🤖 Бот: {bot_choice}\n🤝 <b>НИЧЬЯ!</b>"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=get_games_keyboard())

@bot.message_handler(func=lambda m: m.text == "🎰 СЛОТЫ")
@subscription_required
def game_slots_start_cmd(message):
    bot.send_message(message.chat.id, "💰 <b>ВВЕДИ СТАВКУ (1-100)</b>", parse_mode='HTML', reply_markup=get_back_keyboard())
    bot.register_next_step_handler(message, game_slots_play)

def game_slots_play(message):
    if message.text == "◀️ НАЗАД":
        games_menu_cmd(message)
        return
    try:
        bet = int(message.text)
        if bet < 1 or bet > 100:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ Ставка от 1 до 100", parse_mode='HTML', reply_markup=get_games_keyboard())
        return
    
    user_id = message.from_user.id
    user = get_user(user_id)
    if user['coins'] < bet:
        bot.send_message(message.chat.id, f"❌ Не хватает! У тебя {user['coins']}💰", parse_mode='HTML', reply_markup=get_games_keyboard())
        return
    
    spin, win = play_slots(bet)
    new_coins = user['coins'] + win
    update_user(user_id, coins=new_coins)
    add_xp(user_id, 3)
    
    if win > 0:
        text = f"{' '.join(spin)}\n🎉 <b>ВЫИГРЫШ {win}💰</b>\n💰 Теперь {new_coins}💰"
    else:
        text = f"{' '.join(spin)}\n😔 <b>ПРОИГРЫШ {abs(win)}💰</b>\n💰 Теперь {new_coins}💰"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=get_games_keyboard())

# ========== ДУЭЛЬ С БОТОМ ==========
@bot.message_handler(func=lambda m: m.text == "⚔️ ДУЭЛЬ С БОТОМ")
@subscription_required
def duel_bot_start_cmd(message):
    user_id = message.from_user.id
    duel_bot_games[user_id] = {'player_hp': 100, 'bot_hp': 100, 'player_defending': False, 'bot_defending': False}
    bot.send_message(message.chat.id, "⚔️ <b>ДУЭЛЬ С БОТОМ!</b>\n\n❤️ Твоё HP: 100\n🤖 HP бота: 100\n\nТвой ход!", parse_mode='HTML', reply_markup=get_duel_bot_keyboard())

@bot.message_handler(func=lambda m: m.text in ["⚔️ АТАКОВАТЬ", "🛡️ ЗАЩИТАТЬСЯ", "💊 ЛЕЧЕНИЕ"])
@subscription_required
def duel_bot_action_cmd(message):
    user_id = message.from_user.id
    if user_id not in duel_bot_games:
        duel_bot_start_cmd(message)
        return
    
    game = duel_bot_games[user_id]
    action = message.text
    msg = ""
    
    # Ход игрока
    if action == "⚔️ АТАКОВАТЬ":
        damage = calculate_duel_damage('attack')
        game['bot_hp'] -= damage
        msg += f"⚔️ Ты нанёс {damage} урона!\n"
    elif action == "🛡️ ЗАЩИТАТЬСЯ":
        damage = calculate_duel_damage('defend')
        game['bot_hp'] -= damage
        msg += f"🛡️ Контратака! {damage} урона!\n"
    else:  # ЛЕЧЕНИЕ
        heal = calculate_duel_damage('heal')
        game['player_hp'] = min(100, game['player_hp'] + heal)
        msg += f"💊 Ты вылечил {heal} HP!\n"
    
    if game['bot_hp'] <= 0:
        new_winner_elo, _ = update_elo(get_user(user_id)['elo_rating'], 1000)
        update_user(user_id, wins=get_user(user_id)['wins'] + 1, coins=get_user(user_id)['coins'] + 50, elo_rating=new_winner_elo)
        add_xp(user_id, 30)
        bot.send_message(message.chat.id, f"{msg}\n✅ <b>ПОБЕДА!</b> +50💰 +{new_winner_elo - get_user(user_id)['elo_rating']} рейтинга", parse_mode='HTML', reply_markup=get_games_keyboard())
        del duel_bot_games[user_id]
        return
    
    # Ход бота
    bot_action = random.choice(['attack', 'attack', 'defend'])
    if bot_action == 'attack':
        damage = calculate_duel_damage('attack')
        game['player_hp'] -= damage
        msg += f"🤖 Бот нанёс {damage} урона!\n"
    else:
        damage = calculate_duel_damage('defend')
        game['player_hp'] -= damage
        msg += f"🛡️ Бот контратаковал! {damage} урона!\n"
    
    msg += f"\n❤️ <b>Твоё HP:</b> {max(0, game['player_hp'])}\n🤖 <b>HP бота:</b> {max(0, game['bot_hp'])}"
    
    if game['player_hp'] <= 0:
        new_loser_elo, _ = update_elo(1000, get_user(user_id)['elo_rating'])
        update_user(user_id, losses=get_user(user_id)['losses'] + 1, elo_rating=new_loser_elo)
        bot.send_message(message.chat.id, f"{msg}\n\n💀 <b>ПОРАЖЕНИЕ!</b> {new_loser_elo - get_user(user_id)['elo_rating']} рейтинга", parse_mode='HTML', reply_markup=get_games_keyboard())
        del duel_bot_games[user_id]
    else:
        bot.send_message(message.chat.id, msg, parse_mode='HTML', reply_markup=get_duel_bot_keyboard())

# ========== ДУЭЛЬ С ДРУГОМ (упрощённо) ==========
@bot.message_handler(func=lambda m: m.text == "👥 ДУЭЛЬ С ДРУГОМ")
@subscription_required
def duel_friend_start_cmd(message):
    bot.send_message(message.chat.id, "👥 <b>Введи @username соперника</b>", parse_mode='HTML')
    bot.register_next_step_handler(message, duel_friend_request)

def duel_friend_request(message):
    if message.text == "◀️ НАЗАД":
        games_menu_cmd(message)
        return
    
    challenger_id = message.from_user.id
    opponent_username = message.text.strip().lstrip('@')
    
    cursor = get_user(0)  # костыль для доступа к cursor
    # нужно переделать, но для простоты оставим заглушку
    bot.send_message(message.chat.id, "⚔️ Функция в разработке", parse_mode='HTML', reply_markup=get_games_keyboard())

# ========== КРЕСТИКИ-НОЛИКИ С БОТОМ ==========
@bot.message_handler(func=lambda m: m.text == "❌ КРЕСТИКИ-НОЛИКИ")
@subscription_required
def tictactoe_bot_start_cmd(message):
    user_id = message.from_user.id
    tictactoe_games[user_id] = {'board': list('---------'), 'turn': 'player'}
    markup = create_ttt_bot_keyboard(user_id, '---------')
    bot.send_message(message.chat.id, "❌ <b>КРЕСТИКИ-НОЛИКИ С БОТОМ</b>\n\nТы за X. Твой ход!\n\n" + print_board('---------'), parse_mode='HTML', reply_markup=markup)

def create_ttt_bot_keyboard(user_id, board):
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for i in range(9):
        if board[i] == '-':
            buttons.append(InlineKeyboardButton("⬜", callback_data=f"ttt_bot_{user_id}_{i}"))
        else:
            buttons.append(InlineKeyboardButton(board[i], callback_data="noop"))
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("◀️ ВЫЙТИ", callback_data=f"ttt_bot_exit_{user_id}"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('ttt_bot_'))
def tictactoe_bot_callback(call):
    user_id = call.from_user.id
    data = call.data.split('_')
    
    if data[2] == 'exit':
        if user_id in tictactoe_games:
            del tictactoe_games[user_id]
        bot.edit_message_text("❌ Игра завершена", call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id)
        return
    
    if user_id not in tictactoe_games:
        bot.answer_callback_query(call.id, "Игра не найдена")
        return
    
    game = tictactoe_games[user_id]
    position = int(data[2])
    
    if game['board'][position] != '-':
        bot.answer_callback_query(call.id, "Клетка занята!")
        return
    
    # Ход игрока
    game['board'][position] = 'X'
    winner = check_winner(''.join(game['board']))
    
    if winner:
        if winner == 'X':
            update_user(user_id, wins=get_user(user_id)['wins'] + 1, coins=get_user(user_id)['coins'] + 30)
            add_xp(user_id, 20)
            msg = f"✅ <b>ТЫ ПОБЕДИЛ!</b> +30💰"
        elif winner == 'draw':
            update_user(user_id, draws=get_user(user_id)['draws'] + 1)
            msg = f"🤝 <b>НИЧЬЯ!</b>"
        else:
            msg = "❌ Ошибка"
        
        bot.edit_message_text(f"❌ <b>КРЕСТИКИ-НОЛИКИ</b>\n\n{msg}\n\n{print_board(''.join(game['board']))}", 
                              call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=None)
        del tictactoe_games[user_id]
        bot.answer_callback_query(call.id, msg)
        return
    
    # Ход бота (случайная свободная клетка)
    free_cells = [i for i, v in enumerate(game['board']) if v == '-']
    if free_cells:
        bot_move = random.choice(free_cells)
        game['board'][bot_move] = 'O'
        winner = check_winner(''.join(game['board']))
        
        if winner:
            if winner == 'O':
                update_user(user_id, losses=get_user(user_id)['losses'] + 1)
                msg = f"💀 <b>ТЫ ПРОИГРАЛ</b>"
            elif winner == 'draw':
                update_user(user_id, draws=get_user(user_id)['draws'] + 1)
                msg = f"🤝 <b>НИЧЬЯ!</b>"
            else:
                msg = "❌ Ошибка"
            
            bot.edit_message_text(f"❌ <b>КРЕСТИКИ-НОЛИКИ</b>\n\n{msg}\n\n{print_board(''.join(game['board']))}", 
                                  call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=None)
            del tictactoe_games[user_id]
            bot.answer_callback_query(call.id, msg)
            return
    
    # Обновляем клавиатуру
    markup = create_ttt_bot_keyboard(user_id, ''.join(game['board']))
    bot.edit_message_text(f"❌ <b>КРЕСТИКИ-НОЛИКИ С БОТОМ</b>\n\nТвой ход!\n\n{print_board(''.join(game['board']))}", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "noop")
def noop_callback(call):
    bot.answer_callback_query(call.id)

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 ТОПОВЫЙ БОТ ЗАПУЩЕН")
    print(f"🔑 Триггер в чатах: '{TRIGGER_WORD}'")
    print("🎮 Игры: дуэли, КНБ, слоты, крестики-нолики, кубик")
    print("🏆 Рейтинг ELO")
    print("=" * 60)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            time.sleep(5)
