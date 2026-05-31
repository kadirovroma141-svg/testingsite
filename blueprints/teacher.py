import os
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (db, Test, Question, AnswerOption,
                    AssignedTest, TestResult,
                    TestCreationMethod, TestDifficulty, QuestionType)

teacher_bp = Blueprint("teacher", __name__)

ALLOWED_EXTENSIONS = {"docx"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ================================================================ Dashboard

@teacher_bp.route("/")
@teacher_bp.route("/dashboard")
@login_required
def dashboard():
    my_tests    = Test.query.filter_by(author_id=current_user.id).order_by(Test.updated_at.desc()).limit(5).all()
    my_assigned = AssignedTest.query.filter_by(teacher_id=current_user.id).order_by(AssignedTest.created_at.desc()).limit(5).all()
    # Count results for teacher's tests (including bundle results)
    total_results = (TestResult.query
                     .join(Test, TestResult.test_id == Test.id)
                     .filter(Test.author_id == current_user.id)
                     .count())
    return render_template("teacher/dashboard.html",
                           my_tests=my_tests,
                           my_assigned=my_assigned,
                           total_results=total_results)


# ================================================================ Tests CRUD

@teacher_bp.route("/tests")
@login_required
def tests():
    page  = request.args.get("page", 1, type=int)
    tests = (Test.query
             .filter_by(author_id=current_user.id)
             .order_by(Test.updated_at.desc())
             .paginate(page=page, per_page=12))
    return render_template("teacher/tests.html", pagination=tests)


@teacher_bp.route("/tests/new", methods=["GET", "POST"])
@login_required
def new_test():
    """Landing page to choose creation method."""
    return render_template("teacher/new_test.html")


@teacher_bp.route("/tests/new/manual", methods=["GET"])
@login_required
def new_test_manual():
    test = Test(author_id=current_user.id,
                title="Новый тест",
                creation_method=TestCreationMethod.MANUAL,
                is_draft=True)
    db.session.add(test)
    db.session.commit()
    return redirect(url_for("teacher.edit_test", test_id=test.id))


@teacher_bp.route("/tests/new/docx", methods=["GET", "POST"])
@login_required
def new_test_docx():
    if request.method == "POST":
        file = request.files.get("docx_file")
        if not file or not _allowed_file(file.filename):
            flash("Загрузите файл в формате .docx.", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(path)

        from services.docx_parser import parse_docx_to_test
        try:
            test = parse_docx_to_test(path, author_id=current_user.id)
            flash("Тест успешно импортирован из файла.", "success")
            return redirect(url_for("teacher.edit_test", test_id=test.id))
        except Exception as e:
            flash(f"Ошибка парсинга: {e}", "danger")
            return redirect(request.url)
        finally:
            if os.path.exists(path):
                os.remove(path)

    return render_template("teacher/new_test_docx.html")


@teacher_bp.route("/tests/<int:test_id>/edit", methods=["GET"])
@login_required
def edit_test(test_id: int):
    test = _get_own_test(test_id)
    return render_template("teacher/test_edit.html", test=test)


@teacher_bp.route("/tests/<int:test_id>/delete", methods=["POST"])
@login_required
def delete_test(test_id: int):
    test = _get_own_test(test_id)
    db.session.delete(test)
    db.session.commit()
    flash("Тест удалён.", "success")
    return redirect(url_for("teacher.tests"))


# ================================================================ Assigned Tests

@teacher_bp.route("/tests/<int:test_id>/assign", methods=["GET", "POST"])
@login_required
def assign_test(test_id: int):
    test = _get_own_test(test_id)

    if request.method == "POST":
        from datetime import datetime, timezone

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

        assigned = AssignedTest(
            test_id=test_id,
            teacher_id=current_user.id,
            label=label,
            time_limit_minutes=time_limit,
            max_attempts=max_attempts,
            shuffle_questions=shuffle_q,
            shuffle_options=shuffle_o,
            show_results_to_student=show_results,
            available_from=_parse_dt("available_from"),
            available_until=_parse_dt("available_until"),
        )
        db.session.add(assigned)
        db.session.commit()
        flash(f"Тест назначен! PIN-код: {assigned.pin_code}", "success")
        return redirect(url_for("teacher.assigned_list"))

    return render_template("teacher/assign_test.html", test=test)


@teacher_bp.route("/assigned")
@login_required
def assigned_list():
    page     = request.args.get("page", 1, type=int)
    assigned = (AssignedTest.query
                .filter_by(teacher_id=current_user.id)
                .order_by(AssignedTest.created_at.desc())
                .paginate(page=page, per_page=15))
    return render_template("teacher/assigned.html", pagination=assigned)


@teacher_bp.route("/assigned/<int:aid>/toggle", methods=["POST"])
@login_required
def toggle_assigned(aid: int):
    a = _get_own_assigned(aid)
    a.is_active = not a.is_active
    db.session.commit()
    flash("Статус PIN-кода изменён.", "success")
    return redirect(url_for("teacher.assigned_list"))


@teacher_bp.route("/assigned/<int:aid>/regenerate-pin", methods=["POST"])
@login_required
def regenerate_pin(aid: int):
    a = _get_own_assigned(aid)
    new_pin = a.regenerate_pin()
    db.session.commit()
    flash(f"Новый PIN-код: {new_pin}", "success")
    return redirect(url_for("teacher.assigned_list"))


@teacher_bp.route("/assigned/<int:aid>/delete", methods=["POST"])
@login_required
def delete_assigned(aid: int):
    a = _get_own_assigned(aid)
    db.session.delete(a)
    db.session.commit()
    flash("Назначение удалено.", "success")
    return redirect(url_for("teacher.assigned_list"))


# ================================================================ Results

@teacher_bp.route("/results")
@login_required
def results():
    page   = request.args.get("page", 1, type=int)
    pin    = request.args.get("pin", "").strip()
    grade  = request.args.get("grade", "").strip()
    letter = request.args.get("letter", "").strip()

    # Teacher sees results ONLY for their own tests (including bundles)
    query = (TestResult.query
             .join(Test, TestResult.test_id == Test.id)
             .filter(Test.author_id == current_user.id))

    if pin:
        # Filter by PIN — check both AssignedTest and TestBundle PINs
        from sqlalchemy import or_
        from models import TestBundle
        query = query.outerjoin(AssignedTest, TestResult.assigned_test_id == AssignedTest.id)
        query = query.outerjoin(TestBundle, TestResult.bundle_id == TestBundle.id)
        query = query.filter(
            or_(AssignedTest.pin_code == pin, TestBundle.pin_code == pin)
        )
    if grade:
        query = query.filter(TestResult.student_grade == grade)
    if letter:
        query = query.filter(TestResult.student_letter == letter)

    pagination = query.order_by(TestResult.started_at.desc()).paginate(page=page, per_page=20)
    return render_template("teacher/results.html",
                           pagination=pagination,
                           pin_filter=pin,
                           grade_filter=grade,
                           letter_filter=letter)


@teacher_bp.route("/results/<int:rid>")
@login_required
def result_detail(rid: int):
    # Teacher can see result only if the test belongs to them
    result = (TestResult.query
              .join(Test, TestResult.test_id == Test.id)
              .filter(Test.author_id == current_user.id,
                      TestResult.id == rid)
              .first_or_404())
    answers = result.answer_details.all()
    return render_template("teacher/result_detail.html", result=result, answers=answers)


# ================================================================ Helpers

def _get_own_test(test_id: int) -> Test:
    test = Test.query.filter_by(id=test_id, author_id=current_user.id).first_or_404()
    return test


def _get_own_assigned(aid: int) -> AssignedTest:
    a = AssignedTest.query.filter_by(id=aid, teacher_id=current_user.id).first_or_404()
    return a
