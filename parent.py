import telebot
from telebot import types
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('PARENT_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
DB_NAME = 'rfid_database.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔔 Підписатись"), types.KeyboardButton("🔕 Відписатись"))
    bot.send_message(message.chat.id, "👋 Вітаємо! Цей бот надсилатиме вам сповіщення, коли ваша дитина приходить до школи.\nОберіть дію:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🔔 Підписатись")
def subscribe_start(message):
    msg = bot.send_message(message.chat.id, "Введіть прізвище та ім'я учня (наприклад: Іванов Іван):")
    bot.register_next_step_handler(msg, process_subscription)

def process_subscription(message):
    input_words = set(message.text.strip().lower().split())
    
    if len(input_words) < 2:
        bot.send_message(message.chat.id, "❌ Будь ласка, введіть і прізвище, і ім'я (мінімум 2 слова).")
        return

    conn = get_db_connection()
    users = conn.execute('SELECT name, class_group FROM users').fetchall()
    
    matches = []
    for u in users:
        db_words = set(u['name'].lower().split())
        # Перевіряємо, чи містяться всі введені слова в імені з БД
        if input_words.issubset(db_words):
            matches.append(u)
            
    if len(matches) == 1:
        exact_db_name = matches[0]['name']
        student_class = matches[0]['class_group']
        try:
            conn.execute('INSERT INTO subscriptions (name, chat_id) VALUES (?, ?)', (exact_db_name, message.chat.id))
            conn.commit()
            bot.send_message(message.chat.id, f"✅ Ви успішно підписалися на сповіщення!\n👤 Учень: **{exact_db_name}** ({student_class})", parse_mode="Markdown")
        except sqlite3.IntegrityError:
            bot.send_message(message.chat.id, "⚠️ Ви вже підписані на сповіщення для цього учня.")
    elif len(matches) > 1:
        bot.send_message(message.chat.id, "⚠️ Знайдено кілька учнів з такими даними. Будь ласка, уточніть запит (додайте по батькові).")
    else:
        bot.send_message(message.chat.id, "❌ Учня з такими даними не знайдено в базі.\nПеревірте правильність написання та спробуйте ще раз.")
    
    conn.close()

@bot.message_handler(func=lambda message: message.text == "🔕 Відписатись")
def unsubscribe_start(message):
    msg = bot.send_message(message.chat.id, "Введіть прізвище та ім'я учня, від сповіщень якого хочете відписатись:")
    bot.register_next_step_handler(msg, process_unsubscription)

def process_unsubscription(message):
    input_words = set(message.text.strip().lower().split())
    
    if len(input_words) < 2:
        bot.send_message(message.chat.id, "❌ Будь ласка, введіть і прізвище, і ім'я (мінімум 2 слова).")
        return

    conn = get_db_connection()
    users = conn.execute('SELECT name FROM users').fetchall()
    
    matches = []
    for u in users:
        db_words = set(u['name'].lower().split())
        if input_words.issubset(db_words):
            matches.append(u['name'])

    if len(matches) == 1:
        exact_db_name = matches[0]
        sub = conn.execute('SELECT * FROM subscriptions WHERE name = ? AND chat_id = ?', (exact_db_name, message.chat.id)).fetchone()
        
        if sub:
            conn.execute('DELETE FROM subscriptions WHERE name = ? AND chat_id = ?', (exact_db_name, message.chat.id))
            conn.commit()
            bot.send_message(message.chat.id, "✅ Ви успішно відписалися від сповіщень для цього учня.")
        else:
            bot.send_message(message.chat.id, "❌ Ви не були підписані на цього учня.")
    elif len(matches) > 1:
        bot.send_message(message.chat.id, "⚠️ Знайдено кілька учнів з такими даними. Будь ласка, уточніть запит (додайте по батькові).")
    else:
        bot.send_message(message.chat.id, "❌ Учня з такими даними не знайдено в базі.")
        
    conn.close()

if __name__ == '__main__':
    print("Батьківський бот запущено...")
    bot.infinity_polling()