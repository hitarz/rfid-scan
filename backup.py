import os
import requests
import datetime
import time
import schedule  
from dotenv import load_dotenv
load_dotenv()

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv('PARENT_BOT_TOKEN')
ADMIN_CHAT_ID = '1591165572'
DB_FILENAME = 'rfid_database.db'
# =============================================

def send_backup_to_telegram():
    if not os.path.exists(DB_FILENAME):
        print(f"[{datetime.datetime.now()}] ❌ Файл {DB_FILENAME} не найден!")
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backup_{now}.db"
    caption = f"📦 Автоматичний бекап бази даних SmartSchool\n📅 Дата: {now}"
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    print(f"[{datetime.datetime.now()}] Отправка бэкапа в Telegram...")
    
    try:
        with open(DB_FILENAME, 'rb') as doc:
            files = {'document': (backup_filename, doc)}
            data = {'chat_id': ADMIN_CHAT_ID, 'caption': caption}
            response = requests.post(url, files=files, data=data)
            
        if response.status_code == 200:
            print(f"[{datetime.datetime.now()}] ✅ Успех! Бэкап отправлен.")
        else:
            print(f"[{datetime.datetime.now()}] ❌ Ошибка Telegram API: {response.text}")
            
    except Exception as e:
        print(f"[{datetime.datetime.now()}] ❌ Системная ошибка: {e}")

# ================= ЗАПУСК БОТА =================
if __name__ == '__main__':
    print("🤖 Бот авто-бекапа запущен!")
    
    # Делаем один тестовый бэкап сразу при запуске скрипта
    send_backup_to_telegram()

    # Настраиваем расписание (например, каждый день в 16:00)
    schedule.every().day.at("16:00").do(send_backup_to_telegram)
    
    print("⏳ Ожидание по расписанию (каждый день в 16:00)...")
    
    # Бесконечный цикл: скрипт спит и раз в минуту проверяет, не настало ли время
    while True:
        schedule.run_pending()
        time.sleep(60)