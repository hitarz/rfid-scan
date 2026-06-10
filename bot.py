import telebot
from telebot import types
import sqlite3
import datetime
import calendar
import os
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv('TOKEN')
bot = telebot.TeleBot(TOKEN)
DB_NAME = 'rfid_database.db'
CLASSES = ['5-А', '6-А', '10-А', '10-Б', '10-В', '11-А', '11-Б', '11-В']

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def create_calendar(year, month, cmd):
    markup = types.InlineKeyboardMarkup(row_width=7)
    month_names = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
    markup.row(types.InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="ignore"))
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    row = [types.InlineKeyboardButton(day, callback_data="ignore") for day in days_of_week]
    markup.row(*row)
    
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0: row.append(types.InlineKeyboardButton(" ", callback_data="ignore"))
            else: row.append(types.InlineKeyboardButton(str(day), callback_data=f"{cmd}|{year}-{month:02d}-{day:02d}"))
        markup.row(*row)
    
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    markup.row(
        types.InlineKeyboardButton("◀️", callback_data=f"cal_nav|{cmd}|{prev_year}|{prev_month}"),
        types.InlineKeyboardButton(" ", callback_data="ignore"),
        types.InlineKeyboardButton("▶️", callback_data=f"cal_nav|{cmd}|{next_year}|{next_month}")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📊 Всього людей за день"), types.KeyboardButton("🏫 Звіт по класах"))
    markup.add(types.KeyboardButton("❌ Кого не було"))
    bot.send_message(message.chat.id, "👨‍💻 Адмін-панель. Оберіть дію:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["📊 Всього людей за день", "🏫 Звіт по класах", "❌ Кого не було"])
def request_date(message):
    cmd_map = {"📊 Всього людей за день": "total", "🏫 Звіт по класах": "by_class", "❌ Кого не було": "presence"} # <-- Оновили маппінг
    cmd = cmd_map[message.text]
    now = datetime.datetime.now()
    bot.send_message(message.chat.id, "Оберіть день для звіту:", reply_markup=create_calendar(now.year, now.month, cmd))

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "ignore":
        bot.answer_callback_query(call.id)
        return
    data_parts = call.data.split('|')
    cmd = data_parts[0]

    if cmd == "cal_nav":
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=create_calendar(int(data_parts[2]), int(data_parts[3]), data_parts[1]))
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    conn = get_db_connection()
    target_date = data_parts[1]
    
    if cmd == "total":
        total_count = conn.execute("SELECT COUNT(DISTINCT uid) FROM logs WHERE DATE(scan_time) = ? AND status != 'Поза розкладом'", (target_date,)).fetchone()[0]
        class_counts = conn.execute("SELECT u.class_group, COUNT(DISTINCT l.uid) as count FROM logs l JOIN users u ON l.uid = u.uid WHERE DATE(l.scan_time) = ? AND l.status != 'Поза розкладом' GROUP BY u.class_group ORDER BY u.class_group", (target_date,)).fetchall()
        
        res = f"📅 Дата: {target_date}\n👥 Всього унікальних відвідувань: {total_count}\n\n"
        if class_counts:
            res += "📊 Розподіл по класах:\n" + "\n".join([f"- {row['class_group']}: {row['count']} люд." for row in class_counts])
        else: res += "📊 Відвідувань не зафіксовано."
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=res)

    elif cmd == "by_class":
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(*[types.InlineKeyboardButton(c, callback_data=f"class_rep|{target_date}|{c}") for c in CLASSES])
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"📅 Дата: {target_date}\nОберіть клас:", reply_markup=markup)

    elif cmd == "class_rep":
        selected_class = data_parts[2]
        present = conn.execute("SELECT u.name FROM users u JOIN logs l ON u.uid = l.uid WHERE u.class_group = ? AND DATE(l.scan_time) = ? AND l.status != 'Поза розкладом' GROUP BY u.uid ORDER BY u.name", (selected_class, target_date)).fetchall()
        absent = conn.execute("SELECT name FROM users WHERE class_group = ? AND uid NOT IN (SELECT uid FROM logs WHERE DATE(scan_time) = ? AND status != 'Поза розкладом') ORDER BY name", (selected_class, target_date)).fetchall()
        
        res = f"🏫 **Клас {selected_class}** ({target_date})\n\n✅ **Прийшли:**\n" + ("\n".join([f"- {row['name']}" for row in present]) if present else "- Немає даних")
        res += "\n\n❌ **Не прийшли:**\n" + ("\n".join([f"- {row['name']}" for row in absent]) if absent else "- Немає даних")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=res, parse_mode="Markdown")

    elif cmd == "presence":
        # Залишаємо тільки запит для відсутніх
        absent = conn.execute("SELECT name, class_group FROM users WHERE uid NOT IN (SELECT uid FROM logs WHERE DATE(scan_time) = ? AND status != 'Поза розкладом') AND class_group != 'Не задано' ORDER BY class_group, name", (target_date,)).fetchall()
        
        res_absent = f"📅 Дата: {target_date}\n\n❌ **БУЛИ ВІДСУТНІ:**\n" + ("\n".join([f"- {row['name']} ({row['class_group']})" for row in absent]) if absent else "- Всі на місці!")
        
        # Редагуємо повідомлення з календарем, замінюючи його на список відсутніх
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=res_absent[:4000], parse_mode="Markdown")

if __name__ == '__main__':
    print("Адмін-бот запущено...")
    

    bot.remove_webhook() 
    
    bot.infinity_polling()