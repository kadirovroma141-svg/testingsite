from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, session, jsonify)
from models import (db, AssignedTest, TestBundle, BundleItem, Test,
                    Question, AnswerOption,
                    TestResult, ResultAnswer, QuestionType)
from services.grader import grade_result

student_bp = Blueprint("student", __name__)


def _find_by_pin(pin: str):
    """
    Look up a PIN code. Returns a tuple (source_type, source_obj):
      - ("bundle", TestBundle)
      - ("assigned", AssignedTest)
      - (None, None) if not found
    """
    bundle = TestBundle.query.filter_by(pin_code=pin).first()
    if bundle:
        return "bundle", bundle
    assigned = AssignedTest.query.filter_by(pin_code=pin).first()
    if assigned:
        return "assigned", assigned
    return None, None


@student_bp.route("/", methods=["GET", "POST"])
def index():
    """Landing page: student enters PIN code."""
    if request.method == "POST":
        pin = request.form.get("pin", "").strip().upper()
        source_type, source = _find_by_pin(pin)

        if not source:
            flash("PIN-код не найден. Проверьте и попробуйте снова.", "danger")
            return redirect(url_for("student.index"))

        if not source.is_accessible():
            flash("Этот тест сейчас недоступен (неактивен или вышло время).", "warning")
            return redirect(url_for("student.index"))

        session["pin_code"] = pin
        session["source_type"] = source_type
        return redirect(url_for("student.student_info"))

    return render_template("index.html")


@student_bp.route("/enter-info", methods=["GET", "POST"])
def student_info():
    """Student enters last name, first name, grade, letter."""
    pin = session.get("pin_code")
    source_type = session.get("source_type")
    if not pin or not source_type:
        return redirect(url_for("student.index"))

    _, source = _find_by_pin(pin)
    if not source:
        session.clear()
        return redirect(url_for("student.index"))

    if not source.is_accessible():
        flash("Время действия теста истекло.", "warning")
        session.pop("pin_code", None)
        return redirect(url_for("student.index"))

    # Determine tests to show
    if source_type == "bundle":
        tests_list = [item.test for item in source.items]
        total_questions = sum(t.question_count for t in tests_list)
        time_limit = source.time_limit_minutes
    else:
        tests_list = [source.test]
        total_questions = source.test.question_count
        time_limit = source.time_limit_minutes

    if request.method == "POST":
        last_name  = request.form.get("last_name", "").strip()
        first_name = request.form.get("first_name", "").strip()
        grade      = request.form.get("student_grade", "").strip()
        letter     = request.form.get("student_letter", "").strip()

        if not (last_name and first_name and grade and letter):
            flash("Заполните все поля.", "danger")
            return redirect(request.url)

        # Check attempt limit
        max_attempts = source.max_attempts
        if max_attempts:
            if source_type == "bundle":
                prior = (TestResult.query
                         .filter_by(bundle_id=source.id)
                         .filter(TestResult.student_last_name == last_name,
                                 TestResult.student_first_name == first_name,
                                 TestResult.student_grade == grade,
                                 TestResult.student_letter == letter,
                                 TestResult.is_completed == True)
                         .count())
                # For bundles, count unique attempts (each attempt creates multiple results)
                prior = prior // max(len(tests_list), 1)
            else:
                prior = (TestResult.query
                         .filter_by(assigned_test_id=source.id)
                         .filter(TestResult.student_last_name == last_name,
                                 TestResult.student_first_name == first_name,
                                 TestResult.student_grade == grade,
                                 TestResult.student_letter == letter,
                                 TestResult.is_completed == True)
                         .count())
            if prior >= max_attempts:
                flash("Вы уже исчерпали количество попыток.", "warning")
                return redirect(url_for("student.index"))

        # Create TestResult(s) — one per test
        result_ids = []
        now = datetime.now(timezone.utc)
        for test in tests_list:
            result = TestResult(
                assigned_test_id=source.id if source_type == "assigned" else None,
                bundle_id=source.id if source_type == "bundle" else None,
                test_id=test.id,
                student_last_name=last_name,
                student_first_name=first_name,
                student_grade=grade,
                student_letter=letter,
                started_at=now,
            )
            db.session.add(result)
            db.session.flush()
            result_ids.append(result.id)

        db.session.commit()

        session["result_ids"]  = result_ids
        session["started_at"] = datetime.now(timezone.utc).isoformat()
        return redirect(url_for("student.take_test"))

    return render_template("student/info.html",
                           source=source,
                           source_type=source_type,
                           tests_list=tests_list,
                           total_questions=total_questions,
                           time_limit=time_limit)


@student_bp.route("/test", methods=["GET"])
def take_test():
    """Render the test(s) for the student."""
    result_ids = session.get("result_ids")
    if not result_ids:
        return redirect(url_for("student.index"))

    results = [db.session.get(TestResult, rid) for rid in result_ids]
    results = [r for r in results if r and not r.is_completed]
    if not results:
        session.clear()
        return redirect(url_for("student.index"))

    source_type = session.get("source_type", "assigned")

    # Determine settings
    first_result = results[0]
    if source_type == "bundle" and first_result.bundle:
        source = first_result.bundle
    elif first_result.assigned_test:
        source = first_result.assigned_test
    else:
        session.clear()
        return redirect(url_for("student.index"))

    # Build tabs data (one tab per test)
    import random
    tabs = []
    for result in results:
        test = result.test
        questions = list(test.questions.all())

        if source.shuffle_questions:
            random.shuffle(questions)

        questions_data = []
        for q in questions:
            options = list(q.options.all())
            if source.shuffle_options:
                random.shuffle(options)
            questions_data.append({"question": q, "options": options})

        tabs.append({
            "result": result,
            "test": test,
            "questions_data": questions_data,
        })

    time_limit = source.time_limit_minutes
    show_results = source.show_results_to_student

    return render_template("student/test.html",
                           tabs=tabs,
                           source=source,
                           source_type=source_type,
                           time_limit_minutes=time_limit,
                           show_results=show_results,
                           student=first_result)


@student_bp.route("/test/submit", methods=["POST"])
def submit_test():
    """Accept student answers for all tests and grade them."""
    result_ids = session.get("result_ids")
    if not result_ids:
        return jsonify({"error": "session expired"}), 400

    results = [db.session.get(TestResult, rid) for rid in result_ids]
    results = [r for r in results if r and not r.is_completed]
    if not results:
        return jsonify({"error": "already submitted"}), 400

    data = request.get_json(silent=True) or {}
    answers_payload = data.get("answers", {})   # {question_id: [option_id, ...] or "text"}

    for result in results:
        test = result.test
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

    session.pop("result_ids", None)
    session.pop("started_at", None)
    session.pop("pin_code",   None)
    session.pop("source_type", None)

    # Determine whether to show results
    first_result = results[0]
    source_type = "bundle" if first_result.bundle_id else "assigned"
    if source_type == "bundle":
        show = first_result.bundle.show_results_to_student
    else:
        show = first_result.assigned_test.show_results_to_student

    # Calculate total score across all tests
    total_score = sum(r.score or 0 for r in results)
    total_max   = sum(r.max_score or 0 for r in results)
    total_pct   = round((total_score / total_max * 100) if total_max else 0, 2)

    # Build redirect — use first result ID, result page shows all bundle results
    redirect_url = url_for("student.result_page", rid=results[0].id) if show else url_for("student.index")

    return jsonify({
        "ok":         True,
        "show":       show,
        "score":      total_score,
        "max_score":  total_max,
        "percentage": total_pct,
        "redirect":   redirect_url,
    })


@student_bp.route("/result/<int:rid>")
def result_page(rid: int):
    result = db.session.get(TestResult, rid)
    if not result or not result.is_completed:
        return redirect(url_for("student.index"))

    # Check show permission
    if result.bundle_id and result.bundle:
        show = result.bundle.show_results_to_student
    elif result.assigned_test:
        show = result.assigned_test.show_results_to_student
    else:
        show = False

    if not show:
        flash("Результаты будут доступны позже.", "info")
        return redirect(url_for("student.index"))

    # For bundles, gather all results from the same attempt
    if result.bundle_id:
        all_results = (TestResult.query
                       .filter_by(bundle_id=result.bundle_id,
                                  student_last_name=result.student_last_name,
                                  student_first_name=result.student_first_name,
                                  student_grade=result.student_grade,
                                  student_letter=result.student_letter,
                                  started_at=result.started_at)
                       .all())
    else:
        all_results = [result]

    # Build per-test results with answers
    results_data = []
    for r in all_results:
        answers = r.answer_details.all()
        results_data.append({"result": r, "answers": answers})

    total_score = sum(r.score or 0 for r in all_results)
    total_max   = sum(r.max_score or 0 for r in all_results)
    total_pct   = round((total_score / total_max * 100) if total_max else 0, 2)

    return render_template("student/result.html",
                           result=result,
                           results_data=results_data,
                           total_score=total_score,
                           total_max=total_max,
                           total_pct=total_pct)