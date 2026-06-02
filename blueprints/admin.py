import io
import random
import string
import openpyxl
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from models import (db, User, Test, AssignedTest, TestResult, TestBundle,
                    BundleItem, UserRole)

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


# ================================================================ Dashboard

@admin_bp.route("/")
@admin_bp.route("/dashboard")
def dashboard():
    stats = {
        "teachers":      User.query.filter_by(role=UserRole.TEACHER).count(),
        "tests":         Test.query.count(),
        "assigned":      AssignedTest.query.count(),
        "bundles":       TestBundle.query.count(),
        "results":       TestResult.query.count(),
    }
    recent_results = (
        TestResult.query
        .order_by(TestResult.started_at.desc())
        .limit(10)
        .all()
    )
    return render_template("admin/dashboard.html", stats=stats, recent_results=recent_results)


# ================================================================ Teachers

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


@admin_bp.route("/teachers/<int:uid>/reset-password", methods=["POST"])
def reset_teacher_password(uid: int):
    """Generate a temporary password and force teacher to change it on next login."""
    user = db.session.get(User, uid)
    if not user or user.is_admin:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("admin.teachers"))
    # Generate a readable temporary password: 3 words pattern  e.g. "Kp7#mQ2x"
    chars = string.ascii_letters + string.digits
    temp_password = "".join(random.choices(chars, k=10))
    user.set_password(temp_password)
    user.must_change_password = True
    db.session.commit()
    flash(
        f"Временный пароль для «{user.full_name}»: <strong>{temp_password}</strong> — передайте его учителю. При входе он будет обязан сменить его.",
        "success"
    )
    return redirect(url_for("admin.teachers"))


# ================================================================ Results

@admin_bp.route("/results")
def results():
    page       = request.args.get("page", 1, type=int)
    teacher_id = request.args.get("teacher_id", type=int)
    grade      = request.args.get("grade", "").strip()
    letter     = request.args.get("letter", "").strip()
    pin        = request.args.get("pin", "").strip()
    bundle_id  = request.args.get("bundle_id", type=int)

    from sqlalchemy import or_
    query = (TestResult.query
             .join(Test, TestResult.test_id == Test.id)
             .outerjoin(AssignedTest, TestResult.assigned_test_id == AssignedTest.id)
             .outerjoin(TestBundle, TestResult.bundle_id == TestBundle.id))

    if teacher_id:
        query = query.filter(Test.author_id == teacher_id)
    if grade:
        query = query.filter(TestResult.student_grade == grade)
    if letter:
        query = query.filter(TestResult.student_letter == letter)
    if bundle_id:
        query = query.filter(TestResult.bundle_id == bundle_id)
    elif pin:
        query = query.filter(
            or_(AssignedTest.pin_code == pin, TestBundle.pin_code == pin)
        )

    pagination = query.order_by(TestResult.started_at.desc()).paginate(page=page, per_page=20)
    teachers_list = User.query.filter_by(role=UserRole.TEACHER).order_by(User.full_name).all()

    # Resolve bundle label for display when filtering by bundle
    selected_bundle = db.session.get(TestBundle, bundle_id) if bundle_id else None

    return render_template("admin/results.html",
                           pagination=pagination,
                           teachers=teachers_list,
                           selected_teacher=teacher_id,
                           selected_grade=grade,
                           selected_letter=letter,
                           selected_pin=pin,
                           selected_bundle=selected_bundle,
                           selected_bundle_id=bundle_id)


@admin_bp.route("/results/export")
def export_results():
    teacher_id = request.args.get("teacher_id", type=int)
    grade      = request.args.get("grade", "").strip()
    letter     = request.args.get("letter", "").strip()
    pin        = request.args.get("pin", "").strip()
    bundle_id  = request.args.get("bundle_id", type=int)

    from sqlalchemy import or_
    query = (TestResult.query
             .join(Test, TestResult.test_id == Test.id)
             .outerjoin(AssignedTest, TestResult.assigned_test_id == AssignedTest.id)
             .outerjoin(TestBundle, TestResult.bundle_id == TestBundle.id))

    if teacher_id:
        query = query.filter(Test.author_id == teacher_id)
    if grade:
        query = query.filter(TestResult.student_grade == grade)
    if letter:
        query = query.filter(TestResult.student_letter == letter)
    if bundle_id:
        query = query.filter(TestResult.bundle_id == bundle_id)
    elif pin:
        query = query.filter(
            or_(AssignedTest.pin_code == pin, TestBundle.pin_code == pin)
        )

    all_results = query.order_by(TestResult.started_at.desc()).all()

    # Group by attempt
    from collections import defaultdict
    groups = defaultdict(list)
    for r in all_results:
        key = (r.student_grade, r.student_letter, r.student_last_name, r.student_first_name, r.started_at)
        groups[key].append(r)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Результаты"

    max_tests = max((len(g) for g in groups.values()), default=0)

    headers = ["Класс", "Литер", "Фамилия", "Имя"]
    for i in range(1, max_tests + 1):
        headers.append(f"Предмет {i}")
        headers.append(f"Балл {i}")
        headers.append(f"Оценка {i} (%)")
    headers.extend(["Сумма баллов", "Макс. баллов", "Итоговый %", "Время сдачи", "Дата"])
    ws.append(headers)

    for key, results in groups.items():
        grade_val, letter_val, last_name, first_name, started_at = key
        row = [grade_val, letter_val, last_name, first_name]

        total_score = 0
        total_max = 0
        duration = 0

        for r in results:
            row.append(r.test.subject or r.test.title)
            if r.is_completed:
                pct = round(((r.score or 0) / (r.max_score or 1) * 100), 2)
                row.append(r.score or 0)
                row.append(pct)
                total_score += r.score or 0
                total_max += r.max_score or 0
            else:
                row.append("—")
                row.append("Не завершен")

            if r.duration_seconds and r.duration_seconds > duration:
                duration = r.duration_seconds
        
        for _ in range(max_tests - len(results)):
            row.extend(["", "", ""])

        total_pct = round((total_score / total_max * 100) if total_max else 0, 2)
        dur_str = f"{int(duration // 60)} мин {int(duration % 60)} сек" if duration else "—"
        date_str = started_at.strftime("%d.%m.%Y %H:%M") if started_at else "—"

        row.extend([total_score, total_max, total_pct, dur_str, date_str])
        ws.append(row)

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    response = make_response(out.read())
    response.headers["Content-Disposition"] = "attachment; filename=results.xlsx"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response


# ================================================================ Bundles (multi-test assignment)

@admin_bp.route("/assign", methods=["GET", "POST"])
def assign_bundle():
    """Admin page to create a test bundle (assign multiple tests under one PIN)."""
    if request.method == "POST":
        from datetime import datetime, timezone

        test_ids = request.form.getlist("test_ids", type=int)
        if not test_ids:
            flash("Выберите хотя бы один тест.", "danger")
            return redirect(request.url)

        label         = request.form.get("label", "").strip() or None
        time_limit    = request.form.get("time_limit_minutes", type=int)
        max_attempts  = request.form.get("max_attempts", 1, type=int)
        shuffle_q     = bool(request.form.get("shuffle_questions"))
        shuffle_o     = bool(request.form.get("shuffle_options"))
        show_results  = bool(request.form.get("show_results_to_student", True))

        def _parse_dt(field):
            val = request.form.get(field, "").strip()
            if val:
                try:
                    return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            return None

        bundle = TestBundle(
            label=label,
            created_by_id=current_user.id,
            time_limit_minutes=time_limit,
            max_attempts=max_attempts,
            shuffle_questions=shuffle_q,
            shuffle_options=shuffle_o,
            show_results_to_student=show_results,
            available_from=_parse_dt("available_from"),
            available_until=_parse_dt("available_until"),
        )
        db.session.add(bundle)
        db.session.flush()

        for idx, tid in enumerate(test_ids):
            test = db.session.get(Test, tid)
            if test:
                item = BundleItem(bundle_id=bundle.id, test_id=tid, order_index=idx)
                db.session.add(item)

        db.session.commit()
        flash(f"Пакет тестов создан! PIN-код: {bundle.pin_code}", "success")
        return redirect(url_for("admin.bundles"))

    # GET — show form
    # Group tests by teacher
    teachers_list = (User.query
                     .filter_by(role=UserRole.TEACHER)
                     .order_by(User.full_name)
                     .all())
    all_tests = (Test.query
                 .filter_by(is_draft=False)
                 .order_by(Test.subject, Test.title)
                 .all())
    return render_template("admin/assign_bundle.html",
                           teachers=teachers_list,
                           all_tests=all_tests)


@admin_bp.route("/bundles")
def bundles():
    """List all test bundles."""
    page = request.args.get("page", 1, type=int)
    pagination = (TestBundle.query
                  .order_by(TestBundle.created_at.desc())
                  .paginate(page=page, per_page=15))
    return render_template("admin/bundles.html", pagination=pagination)


@admin_bp.route("/bundles/<int:bid>/toggle", methods=["POST"])
def toggle_bundle(bid: int):
    bundle = db.session.get(TestBundle, bid)
    if not bundle:
        flash("Пакет не найден.", "danger")
        return redirect(url_for("admin.bundles"))
    bundle.is_active = not bundle.is_active
    db.session.commit()
    flash("Статус пакета изменён.", "success")
    return redirect(url_for("admin.bundles"))


@admin_bp.route("/bundles/<int:bid>/regenerate-pin", methods=["POST"])
def regenerate_bundle_pin(bid: int):
    bundle = db.session.get(TestBundle, bid)
    if not bundle:
        flash("Пакет не найден.", "danger")
        return redirect(url_for("admin.bundles"))
    new_pin = bundle.regenerate_pin()
    db.session.commit()
    flash(f"Новый PIN-код: {new_pin}", "success")
    return redirect(url_for("admin.bundles"))


@admin_bp.route("/bundles/<int:bid>/delete", methods=["POST"])
def delete_bundle(bid: int):
    bundle = db.session.get(TestBundle, bid)
    if not bundle:
        flash("Пакет не найден.", "danger")
        return redirect(url_for("admin.bundles"))
    db.session.delete(bundle)
    db.session.commit()
    flash("Пакет удалён.", "success")
    return redirect(url_for("admin.bundles"))
