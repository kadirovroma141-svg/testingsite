"""
DOCX Test Parser
================
Parses a Word document (.docx) into a Test with Questions and AnswerOptions.

Expected document template
---------------------------
Line 1: Test title                   (paragraph, style "Title" or bold)
Line 2: Subject: Математика          (optional metadata)
Line 3: Grade: 10                    (optional metadata)
Line 4: Difficulty: medium           (optional)
---                                   (separator: three dashes)
1. Текст вопроса [single]            (numbered question; [single|multiple|text] optional)
   A) Вариант ответа
   B) Вариант ответа
   C)+ Правильный ответ              (+ marks correct)
   D) Вариант ответа
   Points: 2                         (optional, default 1)
   Explanation: Пояснение            (optional)
---
2. ...

Rules:
- Questions start with a number followed by a period: "1.", "2.", etc.
- Options start with A–H followed by ) : "A)", "B)", ...
- Correct options are marked with + after the letter: "A+)" or "A)+" or just "+"
  at the beginning of the option text.
"""
from __future__ import annotations
import re
from docx import Document
from models import db, Test, Question, AnswerOption, TestCreationMethod, QuestionType

# Regex patterns
RE_QUESTION   = re.compile(r"^\s*(\d+)\.\s+(.+?)(?:\s+\[(single|multiple|text)\])?\s*$", re.I)
RE_OPTION     = re.compile(r"^\s*([A-HА-Е])\s*(\+)?\s*[)\.]\s*(\+)?\s*(.+)$", re.I)
RE_META_KEY   = re.compile(r"^\s*(subject|grade|difficulty|points|explanation)\s*:\s*(.+)$", re.I)
RE_SEPARATOR  = re.compile(r"^\s*-{3,}\s*$")


def _clean(text: str) -> str:
    return text.strip()


def parse_docx_to_test(filepath: str, author_id: int) -> Test:
    doc   = Document(filepath)
    lines = [p.text for p in doc.paragraphs]

    # ---------------------------------------------------------------- header
    title      = "Импортированный тест"
    subject    = None
    grade      = None
    difficulty = "medium"

    content_start = 0
    for i, line in enumerate(lines):
        stripped = _clean(line)
        if not stripped:
            continue
        m = RE_META_KEY.match(stripped)
        if m:
            key, val = m.group(1).lower(), _clean(m.group(2))
            if key == "subject":    subject    = val
            elif key == "grade":    grade      = val
            elif key == "difficulty": difficulty = val
            content_start = i + 1
        elif RE_SEPARATOR.match(stripped):
            content_start = i + 1
            break
        elif i == 0:
            title = stripped
            content_start = 1

    # ---------------------------------------------------------------- questions
    test = Test(
        author_id=author_id,
        title=title,
        subject=subject,
        grade_level=grade,
        difficulty=difficulty,
        creation_method=TestCreationMethod.DOCX,
        is_draft=True,
    )
    db.session.add(test)
    db.session.flush()

    current_q: Question | None  = None
    q_index                     = 0
    current_points: float       = 1.0
    current_explanation: str    = ""

    def _save_question():
        nonlocal current_q
        if current_q is not None:
            current_q.points      = current_points
            current_q.explanation = current_explanation
            db.session.flush()

    for line in lines[content_start:]:
        stripped = _clean(line)
        if not stripped:
            continue

        # --- separator between questions
        if RE_SEPARATOR.match(stripped):
            _save_question()
            current_q           = None
            current_points      = 1.0
            current_explanation = ""
            continue

        # --- new question
        m_q = RE_QUESTION.match(stripped)
        if m_q:
            _save_question()
            current_points      = 1.0
            current_explanation = ""
            q_text     = _clean(m_q.group(2))
            q_type_str = (m_q.group(3) or "single").lower()
            q_type_map = {"single": QuestionType.SINGLE,
                          "multiple": QuestionType.MULTIPLE,
                          "text": QuestionType.TEXT}
            current_q = Question(
                test_id=test.id,
                order_index=q_index,
                question_type=q_type_map.get(q_type_str, QuestionType.SINGLE),
                text=q_text,
            )
            db.session.add(current_q)
            db.session.flush()
            q_index += 1
            continue

        # --- answer option
        m_o = RE_OPTION.match(stripped)
        if m_o and current_q:
            is_correct = bool(m_o.group(2) or m_o.group(3))
            opt_text   = _clean(m_o.group(4))
            # Also mark correct if text itself starts with +
            if opt_text.startswith("+"):
                is_correct = True
                opt_text   = _clean(opt_text[1:])
            db.session.add(AnswerOption(
                question_id=current_q.id,
                order_index=0,   # will sort by insertion order
                text=opt_text,
                is_correct=is_correct,
            ))
            continue

        # --- inline metadata for current question
        m_meta = RE_META_KEY.match(stripped)
        if m_meta and current_q:
            key, val = m_meta.group(1).lower(), _clean(m_meta.group(2))
            if key == "points":
                try:
                    current_points = float(val)
                except ValueError:
                    pass
            elif key == "explanation":
                current_explanation = val
            continue

    _save_question()
    db.session.commit()
    return test
