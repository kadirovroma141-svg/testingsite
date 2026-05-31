import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Загружаем настройки из файла .env
load_dotenv()

# Импортируем Flask-приложение, базу данных и модель Пользователя
try:
    from api.index import app
    from app import db
    # Пытаемся импортировать модель User. Измените импорт, если она лежит в другом месте
    from models import User
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что файлы app.py, models.py и папка api находятся в этой же директории.")
    exit(1)

def create_three_admins():
    print("=== Панель создания администраторов ===")
    print(f"Подключение к базе данных: {os.getenv('DATABASE_URL')[:30]}...\n")

    # Список из 3 администраторов, которых мы создадим
    # Мы добавили обязательное поле "full_name"
    admins_data = [
        {
            "username": "Bekkozha",
            "full_name": "Беккожа Администратор",
            "email": "admin1@school.ru",
            "password": "AdminPassword123!",
            "role": "admin"
        },
        {
            "username": "admin2",
            "full_name": "Второй Администратор",
            "email": "admin2@school.ru",
            "password": "AdminPassword456!",
            "role": "admin"
        },
        {
            "username": "admin3",
            "full_name": "Третий Администратор",
            "email": "admin3@school.ru",
            "password": "AdminPassword789!",
            "role": "admin"
        }
    ]

    with app.app_context():
        for data in admins_data:
            # Проверяем, существует ли уже пользователь с таким email или username
            existing_user = User.query.filter(
                (User.email == data["email"]) | (User.username == data["username"])
            ).first()

            if existing_user:
                print(f"⚠️ Пользователь {data['username']} ({data['email']}) уже существует в базе. Пропускаем...")
                continue

            # Создаем новый объект пользователя
            new_user = User()
            new_user.username = data["username"]
            new_user.email = data["email"]
            
            # Принудительно заполняем обязательное поле full_name
            if hasattr(new_user, 'full_name'):
                new_user.full_name = data["full_name"]

            # Автоматически определяем, какую роль/флаг админа использует ваша модель User
            if hasattr(new_user, 'role'):
                new_user.role = 'admin'
            elif hasattr(new_user, 'is_admin'):
                new_user.is_admin = True
            elif hasattr(new_user, 'is_superuser'):
                new_user.is_superuser = True

            # Хешируем пароль с обработкой отсутствия scrypt на старых macOS / Python 3.9
            try:
                # Пробуем стандартное хеширование (в новых версиях Werkzeug это scrypt)
                hashed_pwd = generate_password_hash(data["password"])
            except AttributeError:
                # Если hashlib на Mac не поддерживает scrypt, принудительно используем классический pbkdf2
                hashed_pwd = generate_password_hash(data["password"], method='pbkdf2:sha256')

            if hasattr(new_user, 'set_password'):
                new_user.set_password(data["password"])
            elif hasattr(new_user, 'password_hash'):
                new_user.password_hash = hashed_pwd
            elif hasattr(new_user, 'password'):
                new_user.password = hashed_pwd
            else:
                print(f"❌ Не удалось определить поле для пароля у модели User.")
                return

            try:
                db.session.add(new_user)
                db.session.commit()
                print(f"✅ Администратор '{data['username']}' успешно создан!")
                print(f"   Логин: {data['email']}")
                print(f"   Пароль: {data['password']}\n")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Ошибка при создании {data['username']}: {e}")

        print("=== Процесс завершен ===")

if __name__ == "__main__":
    create_three_admins()