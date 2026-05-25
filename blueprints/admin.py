from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, User, Test, AssignedTest, TestResult, UserRole

admin_bp = Blueprint("admin", __name__)


def _admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Доступ только для администраторов.", "danger")
        return redirect(url_for("auth.login"))
    return None


@admin_bp.before_request
@login_required
def check_admin():
    if not current_user.is_admin:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for("auth.login"))


@admin_bp.route("/")
@admin_bp.route("/dashboard")
def dashboard():
    stats = {
        "teachers":      User.query.filter_by(role=UserRole.TEACHER).count(),
        "tests":         Test.query.count(),
        "assigned":      AssignedTest.query.count(),
        "results":       TestResult.query.count(),
    }
    recent_results = (
        TestResult.query
        .order_by(TestResult.started_at.desc())
        .limit(10)
        .all()
    )
    return render_template("admin/dashboard.html", stats=stats, recent_results=recent_results)


@admin_bp.route("/teachers")
def teachers():
    teachers_list = User.query.filter_by(role=UserRole.TEACHER).order_by(User.full_name).all()
    return render_template("admin/teachers.html", teachers=teachers_list)


@admin_bp.route("/teachers/<int:uid>/toggle", methods=["POST"])
def toggle_teacher(uid: int):
    user = db.session.get(User, uid)
    if not user or user.is_admin:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("admin.teachers"))
    user.is_active = not user.is_active
    db.session.commit()
    status = "активирован" if user.is_active else "деактивирован"
    flash(f"Учитель «{user.full_name}» {status}.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:uid>/delete", methods=["POST"])
def delete_teacher(uid: int):
    user = db.session.get(User, uid)
    if not user or user.is_admin:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("admin.teachers"))
    db.session.delete(user)
    db.session.commit()
    flash(f"Учитель удалён.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/results")
def results():
    page = request.args.get("page", 1, type=int)
    teacher_id = request.args.get("teacher_id", type=int)

    query = TestResult.query.join(AssignedTest).join(Test)
    if teacher_id:
        query = query.filter(Test.author_id == teacher_id)

    pagination = query.order_by(TestResult.started_at.desc()).paginate(page=page, per_page=20)
    teachers_list = User.query.filter_by(role=UserRole.TEACHER).order_by(User.full_name).all()
    return render_template("admin/results.html",
                           pagination=pagination,
                           teachers=teachers_list,
                           selected_teacher=teacher_id)
