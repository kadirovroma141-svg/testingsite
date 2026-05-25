"""
create_admin.py — Run once to create the first admin account.
Usage: python create_admin.py
"""
from app import create_app
from models import db, User, UserRole

app = create_app()

with app.app_context():
    username  = input("Логин администратора: ").strip()
    email     = input("Email: ").strip()
    full_name = input("ФИО: ").strip()
    password  = input("Пароль: ").strip()

    if User.query.filter_by(username=username).first():
        print("❌ Пользователь с таким логином уже существует.")
    else:
        admin = User(username=username, email=email,
                     full_name=full_name, role=UserRole.ADMIN)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Администратор «{full_name}» создан успешно!")
