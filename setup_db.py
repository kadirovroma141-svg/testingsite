import os
from dotenv import load_dotenv

# Принудительно читаем .env файл
load_dotenv()

print("1. Подключаемся к базе:", os.getenv('DATABASE_URL'))

# Импортируем приложение и базу
from api.index import app
from app import db

# САМОЕ ВАЖНОЕ: Импортируем ваши модели, чтобы Flask их увидел!
import models  

# Создаем таблицы
with app.app_context():
    print("2. Начинаю создание таблиц...")
    db.create_all()
    print("3. ГОТОВО! Все таблицы успешно созданы. Идите проверять Supabase!")