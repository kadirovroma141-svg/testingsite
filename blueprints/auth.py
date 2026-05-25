from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, UserRole

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            return redirect(next_page or _url_by_role(user))

        flash("Неверный логин или пароль.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    """Only admins can create new teacher accounts."""
    if not current_user.is_admin:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username  = request.form.get("username", "").strip()
        email     = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password  = request.form.get("password", "")
        role      = request.form.get("role", UserRole.TEACHER)

        errors = []
        if not username:  errors.append("Логин обязателен.")
        if not email:     errors.append("Email обязателен.")
        if not full_name: errors.append("ФИО обязательно.")
        if len(password) < 6: errors.append("Пароль минимум 6 символов.")
        if User.query.filter_by(username=username).first(): errors.append("Логин уже занят.")
        if User.query.filter_by(email=email).first():       errors.append("Email уже занят.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            user = User(username=username, email=email, full_name=full_name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Пользователь «{full_name}» успешно создан.", "success")
            return redirect(url_for("admin.teachers"))

    return render_template("auth/register.html")


# ------------------------------------------------------------------ helpers

def _redirect_by_role(user: User):
    return redirect(_url_by_role(user))


def _url_by_role(user: User) -> str:
    if user.is_admin:
        return url_for("admin.dashboard")
    return url_for("teacher.dashboard")
