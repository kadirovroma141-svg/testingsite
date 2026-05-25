"""
API Blueprint — AJAX endpoints for:
  - AI test generation
  - Test/question CRUD (used by the JS test builder)
  - Image upload
"""
import os
import uuid
import json
from flask import Blueprint, request, jsonify, current_app, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import (db, Test, Question, AnswerOption,
                    TestCreationMethod, QuestionType)

api_bp = Blueprint("api", __name__)

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def _allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


# ============================================================== Image Upload

@api_bp.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    """Upload an image and return its URL."""
    file = request.files.get("image")
    if not file or not _allowed_image(file.filename):
        return jsonify({"error": "Загрузите изображение (png, jpg, gif, webp, svg)."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.static_folder, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, unique_name))

    image_url = url_for("static", filename=f"uploads/{unique_name}")
    return jsonify({"url": image_url})


# ============================================================== AI Generation

@api_bp.route("/generate-test", methods=["POST"])
@login_required
def generate_test():
    data       = request.get_json(silent=True) or {}
    topic      = data.get("topic", "").strip()
    difficulty = data.get("difficulty", "medium")
    count      = int(data.get("count", 10))
    subject    = data.get("subject", "").strip()
    language   = data.get("language", "ru")

    if not topic:
        return jsonify({"error": "Укажите тему теста."}), 400
    if not (1 <= count <= 50):
        return jsonify({"error": "Количество вопросов: от 1 до 50."}), 400

    from services.ai_generator import generate_questions_json
    try:
        questions_data = generate_questions_json(
            topic=topic, difficulty=difficulty,
            count=count, language=language
        )
    except Exception as e:
        current_app.logger.error("AI generation error: %s", e)
        return jsonify({"error": f"Ошибка генерации: {e}"}), 500

    test = Test(
        author_id=current_user.id,
        title=f"{topic} ({difficulty})",
        subject=subject,
        difficulty=difficulty,
        creation_method=TestCreationMethod.AI,
        is_draft=True,
    )
    db.session.add(test)
    db.session.flush()

    for idx, q_data in enumerate(questions_data):
        q = Question(
            test_id=test.id,
            order_index=idx,
            question_type=q_data.get("type", QuestionType.SINGLE),
            text=q_data.get("text", ""),
            points=float(q_data.get("points", 1.0)),
            explanation=q_data.get("explanation", ""),
        )
        db.session.add(q)
        db.session.flush()

        for oi, opt in enumerate(q_data.get("options", [])):
            ao = AnswerOption(
                question_id=q.id,
                order_index=oi,
                text=opt.get("text", ""),
                is_correct=bool(opt.get("is_correct", False)),
            )
            db.session.add(ao)

    db.session.commit()
    return jsonify({"test_id": test.id, "title": test.title, "question_count": len(questions_data)})


# ============================================================== Test meta update

@api_bp.route("/tests/<int:test_id>", methods=["PATCH"])
@login_required
def update_test_meta(test_id: int):
    test = Test.query.filter_by(id=test_id, author_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    for field in ("title", "description", "subject", "grade_level", "difficulty"):
        if field in data:
            setattr(test, field, data[field])
    db.session.commit()
    return jsonify({"ok": True})


# ============================================================== Question CRUD

@api_bp.route("/tests/<int:test_id>/questions", methods=["GET"])
@login_required
def get_questions(test_id: int):
    test = Test.query.filter_by(id=test_id, author_id=current_user.id).first_or_404()
    result = []
    for q in test.questions.all():
        result.append({
            "id":            q.id,
            "order_index":   q.order_index,
            "question_type": q.question_type,
            "text":          q.text,
            "image_url":     q.image_url,
            "points":        q.points,
            "explanation":   q.explanation,
            "options": [
                {"id": o.id, "text": o.text,
                 "is_correct": o.is_correct, "order_index": o.order_index,
                 "image_url": o.image_url}
                for o in q.options.all()
            ],
        })
    return jsonify(result)


@api_bp.route("/tests/<int:test_id>/questions", methods=["POST"])
@login_required
def add_question(test_id: int):
    test = Test.query.filter_by(id=test_id, author_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    q_type = data.get("question_type", QuestionType.SINGLE)
    opts = data.get("options", [])
    
    if q_type == QuestionType.MULTIPLE:
        correct_count = sum(1 for o in opts if o.get("is_correct"))
        if correct_count > 3:
            return jsonify({"error": "Максимум 3 правильных варианта для множественного выбора."}), 400

    last_idx = db.session.query(db.func.max(Question.order_index)).filter_by(test_id=test_id).scalar() or -1
    q = Question(
        test_id=test_id,
        order_index=last_idx + 1,
        question_type=q_type,
        text=data.get("text", "Новый вопрос"),
        points=1.0 if q_type == QuestionType.SINGLE else 2.0,
        explanation=data.get("explanation", ""),
        image_url=data.get("image_url"),
    )
    db.session.add(q)
    db.session.flush()

    for oi, opt in enumerate(opts):
        db.session.add(AnswerOption(
            question_id=q.id, order_index=oi,
            text=opt.get("text", ""), is_correct=bool(opt.get("is_correct", False)),
            image_url=opt.get("image_url"),
        ))

    db.session.commit()
    return jsonify({"id": q.id, "order_index": q.order_index}), 201


@api_bp.route("/questions/<int:qid>", methods=["PATCH"])
@login_required
def update_question(qid: int):
    q    = Question.query.join(Test).filter(Test.author_id == current_user.id, Question.id == qid).first_or_404()
    data = request.get_json(silent=True) or {}
    for field in ("text", "question_type", "explanation", "order_index", "image_url"):
        if field in data:
            setattr(q, field, data[field])
            
    q.points = 1.0 if q.question_type == QuestionType.SINGLE else 2.0

    if "options" in data:
        opts = data["options"]
        if q.question_type == QuestionType.MULTIPLE:
            correct_count = sum(1 for o in opts if o.get("is_correct"))
            if correct_count > 3:
                return jsonify({"error": "Максимум 3 правильных варианта для множественного выбора."}), 400

        AnswerOption.query.filter_by(question_id=q.id).delete()
        db.session.flush()
        for oi, opt in enumerate(opts):
            db.session.add(AnswerOption(
                question_id=q.id, order_index=oi,
                text=opt.get("text", ""), is_correct=bool(opt.get("is_correct", False)),
                image_url=opt.get("image_url"),
            ))

    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/questions/<int:qid>", methods=["DELETE"])
@login_required
def delete_question(qid: int):
    q = Question.query.join(Test).filter(Test.author_id == current_user.id, Question.id == qid).first_or_404()
    db.session.delete(q)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/questions/reorder", methods=["POST"])
@login_required
def reorder_questions():
    """Accept [{id: X, order_index: Y}, ...] and update order."""
    data = request.get_json(silent=True) or []
    for item in data:
        q = Question.query.join(Test).filter(
            Test.author_id == current_user.id,
            Question.id == item["id"]
        ).first()
        if q:
            q.order_index = item["order_index"]
    db.session.commit()
    return jsonify({"ok": True})
