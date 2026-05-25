"""
Grader service — convenience helpers for scoring logic.
The primary scoring happens inside student.py at submit time,
but this module provides reusable functions for re-grading or partial credit.
"""
from __future__ import annotations
from models import TestResult, ResultAnswer, Question, AnswerOption, QuestionType, db


def grade_result(result: TestResult) -> None:
    """
    (Re-)grade all ResultAnswers for the given TestResult
    and update score / max_score / percentage on the result.
    Used by admin for manual re-grading.
    """
    answers: list[ResultAnswer] = result.answer_details.all()
    for ra in answers:
        q: Question = ra.question
        if q.question_type == QuestionType.TEXT:
            # Text questions require manual grading — skip unless already set
            continue

        correct_ids = {o.id for o in q.options.all() if o.is_correct}
        selected    = set(ra.selected_ids_list)

        # Force points_possible dynamically to be safe
        ra.points_possible = 1.0 if q.question_type == QuestionType.SINGLE else 2.0

        if q.question_type == QuestionType.SINGLE:
            ra.is_correct = (selected == correct_ids)
            ra.points_earned = 1.0 if ra.is_correct else 0.0
        else:
            # Multiple Choice logic
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

    db.session.flush()
    result.calculate_score()
    db.session.commit()


def score_summary(result: TestResult) -> dict:
    """Return a dict with scoring breakdown per question."""
    summary = []
    for ra in result.answer_details.all():
        q = ra.question
        summary.append({
            "question_id":    q.id,
            "question_text":  q.text,
            "question_type":  q.question_type,
            "points_possible": ra.points_possible,
            "points_earned":  ra.points_earned,
            "is_correct":     ra.is_correct,
        })
    return {
        "student":    result.student_full_name,
        "score":      result.score,
        "max_score":  result.max_score,
        "percentage": result.percentage,
        "questions":  summary,
    }
