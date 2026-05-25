from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, session, jsonify)
from models import (db, AssignedTest, Test, Question, AnswerOption,
                    TestResult, ResultAnswer, QuestionType)
from services.grader import grade_result

student_bp = Blueprint("student", __name__)


@student_bp.route("/", methods=["GET", "POST"])
def index():
    """Landing page: student enters PIN code."""
    if request.method == "POST":
        pin = request.form.get("pin", "").strip().upper()
        assigned = AssignedTest.query.filter_by(pin_code=pin).first()

        if not assigned:
            flash("PIN-код не найден. Проверьте и попробуйте снова.", "danger")
            return redirect(url_for("student.index"))

        if not assigned.is_accessible():
            flash("Этот тест сейчас недоступен (неактивен или вышло время).", "warning")
            return redirect(url_for("student.index"))

        session["pin_code"] = pin
        return redirect(url_for("student.student_info"))

    return render_template("index.html")


@student_bp.route("/enter-info", methods=["GET", "POST"])
def student_info():
    """Student enters last name, first name, class."""
    pin = session.get("pin_code")
    if not pin:
        return redirect(url_for("student.index"))

    assigned = AssignedTest.query.filter_by(pin_code=pin).first_or_404()

    if not assigned.is_accessible():
        flash("Время действия теста истекло.", "warning")
        session.pop("pin_code", None)
        return redirect(url_for("student.index"))

    if request.method == "POST":
        last_name  = request.form.get("last_name", "").strip()
        first_name = request.form.get("first_name", "").strip()
        klass      = request.form.get("student_class", "").strip()

        if not (last_name and first_name and klass):
            flash("Заполните все поля.", "danger")
            return redirect(request.url)

        # Check attempt limit
        if assigned.max_attempts:
            prior = (TestResult.query
                     .filter_by(assigned_test_id=assigned.id)
                     .filter(TestResult.student_last_name == last_name,
                             TestResult.student_first_name == first_name,
                             TestResult.student_class == klass,
                             TestResult.is_completed == True)
                     .count())
            if prior >= assigned.max_attempts:
                flash("Вы уже исчерпали количество попыток.", "warning")
                return redirect(url_for("student.index"))

        result = TestResult(
            assigned_test_id=assigned.id,
            student_last_name=last_name,
            student_first_name=first_name,
            student_class=klass,
        )
        db.session.add(result)
        db.session.commit()

        session["result_id"]   = result.id
        session["started_at"]  = datetime.now(timezone.utc).isoformat()
        return redirect(url_for("student.take_test"))

    return render_template("student/info.html", assigned=assigned)


@student_bp.route("/test", methods=["GET"])
def take_test():
    """Render the test for the student."""
    result_id = session.get("result_id")
    if not result_id:
        return redirect(url_for("student.index"))

    result   = db.session.get(TestResult, result_id)
    if not result or result.is_completed:
        session.clear()
        return redirect(url_for("student.index"))

    assigned = result.assigned_test
    test     = assigned.test
    questions = list(test.questions.all())

    import random
    if assigned.shuffle_questions:
        random.shuffle(questions)

    questions_data = []
    for q in questions:
        options = list(q.options.all())
        if assigned.shuffle_options:
            random.shuffle(options)
        questions_data.append({"question": q, "options": options})

    time_limit = assigned.time_limit_minutes
    return render_template("student/test.html",
                           result=result,
                           assigned=assigned,
                           test=test,
                           questions_data=questions_data,
                           time_limit_minutes=time_limit)


@student_bp.route("/test/submit", methods=["POST"])
def submit_test():
    """Accept student answers and grade the test."""
    result_id = session.get("result_id")
    if not result_id:
        return jsonify({"error": "session expired"}), 400

    result = db.session.get(TestResult, result_id)
    if not result or result.is_completed:
        return jsonify({"error": "already submitted"}), 400

    data = request.get_json(silent=True) or {}
    answers_payload = data.get("answers", {})   # {question_id: [option_id, ...] or "text"}

    test      = result.assigned_test.test
    questions = test.questions.all()

    for q in questions:
        ra = ResultAnswer(result_id=result.id,
                          question_id=q.id,
                          points_possible=q.points)

        raw = answers_payload.get(str(q.id))
        if q.question_type == QuestionType.TEXT:
            ra.text_answer = str(raw) if raw else ""
            ra.is_correct  = None   # manual grading
            ra.points_earned = 0.0
        else:
            ids = [int(x) for x in (raw or []) if str(x).isdigit()]
            ra.selected_ids_list = ids
            correct_ids = {o.id for o in q.options.all() if o.is_correct}
            selected    = set(ids)

            ra.points_possible = 1.0 if q.question_type == QuestionType.SINGLE else 2.0

            if q.question_type == QuestionType.SINGLE:
                ra.is_correct   = (selected == correct_ids)
                ra.points_earned = 1.0 if ra.is_correct else 0.0
            else:
                errors = len(correct_ids - selected) + len(selected - correct_ids)
                if errors == 0:
                    ra.is_correct = True
                    ra.points_earned = 2.0
                elif errors == 1:
                    ra.is_correct = False
                    ra.points_earned = 1.0
                else:
                    ra.is_correct = False
                    ra.points_earned = 0.0

        db.session.add(ra)

    result.submitted_at = datetime.now(timezone.utc)
    result.is_completed = True
    result.calculate_score()
    db.session.commit()

    session.pop("result_id",  None)
    session.pop("started_at", None)
    session.pop("pin_code",   None)

    show = result.assigned_test.show_results_to_student
    return jsonify({
        "ok":         True,
        "show":       show,
        "score":      result.score,
        "max_score":  result.max_score,
        "percentage": result.percentage,
        "redirect":   url_for("student.result_page", rid=result.id) if show else url_for("student.index")
    })


@student_bp.route("/result/<int:rid>")
def result_page(rid: int):
    result = db.session.get(TestResult, rid)
    if not result or not result.is_completed:
        return redirect(url_for("student.index"))
    show = result.assigned_test.show_results_to_student
    if not show:
        flash("Результаты будут доступны позже.", "info")
        return redirect(url_for("student.index"))
    answers = result.answer_details.all()
    return render_template("student/result.html", result=result, answers=answers)
