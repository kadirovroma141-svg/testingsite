from __future__ import annotations
"""
models.py — Database models for the School Testing Platform.

Entity relationships:
  User (Teacher/Admin)
    └── creates many Tests
    └── creates many AssignedTests (PIN codes)
    └── creates many TestBundles (admin only)

  Test
    └── has many Questions
         └── has many AnswerOptions
    └── can be assigned many times via AssignedTest
    └── can be included in many TestBundles via BundleItem

  TestBundle (multi-test PIN code, created by admin)
    └── has many BundleItems (each pointing to a Test)
    └── has many TestResults (student attempts)

  AssignedTest (single-test PIN code)
    └── belongs to one Test
    └── created by one Teacher (User)
    └── has many TestResults (student attempts)

  TestResult
    └── belongs to one AssignedTest OR one TestBundle
    └── always linked to one Test
    └── has many ResultAnswers (per-question answers)
"""

import random
import string
from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _generate_pin(length: int = 6) -> str:
    """Generate a random numeric PIN of the given length."""
    return "".join(random.choices(string.digits, k=length))


# ---------------------------------------------------------------------------
# Enumerations (stored as plain strings for SQLite compatibility)
# ---------------------------------------------------------------------------

class UserRole:
    ADMIN   = "admin"
    TEACHER = "teacher"


class QuestionType:
    SINGLE   = "single"    # One correct answer (radio)
    MULTIPLE = "multiple"  # Several correct answers (checkbox)
    TEXT     = "text"      # Free-text answer


class TestDifficulty:
    EASY   = "easy"
    MEDIUM = "medium"
    HARD   = "hard"


class TestCreationMethod:
    MANUAL = "manual"
    DOCX   = "docx"
    AI     = "ai"


# ---------------------------------------------------------------------------
# User  (Administrators & Teachers only — students are anonymous)
# ---------------------------------------------------------------------------

class User(db.Model, UserMixin):
    """
    Platform users: administrators and teachers.
    Students do NOT have accounts — they authenticate with a PIN code.
    """
    __tablename__ = "users"

    id                  = db.Column(db.Integer, primary_key=True)
    username            = db.Column(db.String(64),  unique=True, nullable=False, index=True)
    email               = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash       = db.Column(db.String(256), nullable=False)
    full_name           = db.Column(db.String(128), nullable=False)
    role                = db.Column(db.String(16),  nullable=False, default=UserRole.TEACHER)
    is_active           = db.Column(db.Boolean,     nullable=False, default=True)
    must_change_password = db.Column(db.Boolean,    nullable=False, default=False)  # True = teacher must set new password
    created_at          = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at          = db.Column(db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    tests          = db.relationship("Test",         back_populates="author",  lazy="dynamic", cascade="all, delete-orphan")
    assigned_tests = db.relationship("AssignedTest", back_populates="teacher", lazy="dynamic", cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_teacher(self) -> bool:
        return self.role == UserRole.TEACHER

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


# ---------------------------------------------------------------------------
# Test  (the reusable template — contains questions, NOT a live session)
# ---------------------------------------------------------------------------

class Test(db.Model):
    """
    A test template created by a teacher.
    The same Test can be assigned to multiple classes under different PIN codes
    via the AssignedTest model.
    """
    __tablename__ = "tests"

    id               = db.Column(db.Integer, primary_key=True)
    author_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title            = db.Column(db.String(256), nullable=False)
    description      = db.Column(db.Text,        nullable=True)
    subject          = db.Column(db.String(128),  nullable=True)  # e.g. "Математика"
    grade_level      = db.Column(db.String(16),   nullable=True)  # e.g. "10", "11"
    difficulty       = db.Column(db.String(16),   nullable=True, default=TestDifficulty.MEDIUM)
    creation_method  = db.Column(db.String(16),   nullable=False, default=TestCreationMethod.MANUAL)
    is_draft         = db.Column(db.Boolean,      nullable=False, default=True)  # True = not yet published
    created_at       = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at       = db.Column(db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    author         = db.relationship("User",         back_populates="tests")
    questions      = db.relationship("Question",     back_populates="test",
                                     lazy="dynamic",  cascade="all, delete-orphan",
                                     order_by="Question.order_index")
    assigned_tests = db.relationship("AssignedTest", back_populates="test",
                                     lazy="dynamic",  cascade="all, delete-orphan")

    @property
    def question_count(self) -> int:
        return self.questions.count()

    def __repr__(self) -> str:
        return f"<Test id={self.id} title={self.title!r} draft={self.is_draft}>"


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------

class Question(db.Model):
    """
    A single question inside a Test.
    Supports single-choice, multiple-choice, and free-text question types.
    """
    __tablename__ = "questions"

    id           = db.Column(db.Integer, primary_key=True)
    test_id      = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False, index=True)
    order_index  = db.Column(db.Integer, nullable=False, default=0)   # display order within the test
    question_type = db.Column(db.String(16), nullable=False, default=QuestionType.SINGLE)
    text         = db.Column(db.Text, nullable=False)
    image_url    = db.Column(db.String(512), nullable=True)           # optional image attachment
    points       = db.Column(db.Float,   nullable=False, default=1.0) # score value for correct answer
    explanation  = db.Column(db.Text,    nullable=True)               # shown after test completion

    # Relationships
    test    = db.relationship("Test",         back_populates="questions")
    options = db.relationship("AnswerOption", back_populates="question",
                              lazy="dynamic",  cascade="all, delete-orphan",
                              order_by="AnswerOption.order_index")

    def __repr__(self) -> str:
        return f"<Question id={self.id} test_id={self.test_id} type={self.question_type}>"


# ---------------------------------------------------------------------------
# AnswerOption  (choices for a Question)
# ---------------------------------------------------------------------------

class AnswerOption(db.Model):
    """
    One selectable answer option belonging to a Question.
    For TEXT questions this table is not used.
    """
    __tablename__ = "answer_options"

    id          = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    text        = db.Column(db.Text,    nullable=False)
    is_correct  = db.Column(db.Boolean, nullable=False, default=False)
    image_url   = db.Column(db.String(512), nullable=True)           # optional image for this option

    # Relationship
    question = db.relationship("Question", back_populates="options")

    def __repr__(self) -> str:
        return f"<AnswerOption id={self.id} question_id={self.question_id} correct={self.is_correct}>"


# ---------------------------------------------------------------------------
# AssignedTest  (live session — holds the PIN code and scheduling settings)
# ---------------------------------------------------------------------------

class AssignedTest(db.Model):
    """
    Represents one "assignment" of a Test to a specific class/group.
    Each assignment has its own unique PIN code, time limit, and activation window.

    One Test can have many AssignedTests (e.g., same test for 10-A and 10-B
    under different PIN codes, possibly with different time limits).
    """
    __tablename__ = "assigned_tests"

    id              = db.Column(db.Integer, primary_key=True)
    test_id         = db.Column(db.Integer, db.ForeignKey("tests.id"),  nullable=False, index=True)
    teacher_id      = db.Column(db.Integer, db.ForeignKey("users.id"),  nullable=False, index=True)

    # ------------------------------------------------------------------
    # PIN / access settings
    # ------------------------------------------------------------------
    pin_code        = db.Column(db.String(16),  unique=True, nullable=False, default=_generate_pin, index=True)
    label           = db.Column(db.String(128), nullable=True)   # e.g. "10-А, 2026-05-23"
    is_active       = db.Column(db.Boolean,     nullable=False, default=True)

    # ------------------------------------------------------------------
    # Scheduling window (both optional)
    # ------------------------------------------------------------------
    available_from  = db.Column(db.DateTime(timezone=True), nullable=True)  # opens at this time
    available_until = db.Column(db.DateTime(timezone=True), nullable=True)  # closes at this time

    # ------------------------------------------------------------------
    # Per-assignment time limit (minutes).  None = inherit from Test (no limit)
    # ------------------------------------------------------------------
    time_limit_minutes = db.Column(db.Integer, nullable=True)

    # ------------------------------------------------------------------
    # Randomization flags
    # ------------------------------------------------------------------
    shuffle_questions = db.Column(db.Boolean, nullable=False, default=False)
    shuffle_options   = db.Column(db.Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------
    # Show results to student immediately after submission?
    # ------------------------------------------------------------------
    show_results_to_student = db.Column(db.Boolean, nullable=False, default=True)

    # ------------------------------------------------------------------
    # Maximum number of attempts per student (None = unlimited)
    # ------------------------------------------------------------------
    max_attempts    = db.Column(db.Integer, nullable=True, default=1)

    created_at      = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at      = db.Column(db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    test    = db.relationship("Test",         back_populates="assigned_tests")
    teacher = db.relationship("User",         back_populates="assigned_tests", foreign_keys=[teacher_id])
    results = db.relationship("TestResult",   back_populates="assigned_test",
                              lazy="dynamic",  cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_accessible(self) -> bool:
        """Return True if the assignment is currently open for students."""
        if not self.is_active:
            return False
        # Use timezone-aware UTC — required for PostgreSQL compatibility.
        # SQLite also works fine with aware datetimes.
        now = datetime.now(timezone.utc)
        if self.available_from  and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True

    def regenerate_pin(self) -> str:
        """Generate and save a brand-new PIN code."""
        self.pin_code = _generate_pin()
        return self.pin_code

    def __repr__(self) -> str:
        return f"<AssignedTest id={self.id} pin={self.pin_code!r} active={self.is_active}>"


# ---------------------------------------------------------------------------
# TestBundle  (multi-test PIN code — groups several tests under one PIN)
# ---------------------------------------------------------------------------

class TestBundle(db.Model):
    """
    A bundle of tests assigned under a single PIN code.
    Created by an admin, can contain tests from different teachers.
    Students see all tests in the bundle when they enter the PIN.
    Teachers see results only for their own tests within the bundle.
    """
    __tablename__ = "test_bundles"

    id              = db.Column(db.Integer, primary_key=True)
    pin_code        = db.Column(db.String(16),  unique=True, nullable=False, default=_generate_pin, index=True)
    label           = db.Column(db.String(256), nullable=True)
    created_by_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    is_active       = db.Column(db.Boolean,     nullable=False, default=True)

    # Scheduling
    available_from     = db.Column(db.DateTime(timezone=True), nullable=True)
    available_until    = db.Column(db.DateTime(timezone=True), nullable=True)
    time_limit_minutes = db.Column(db.Integer, nullable=True)
    max_attempts       = db.Column(db.Integer, nullable=True, default=1)

    # Randomization & results
    shuffle_questions       = db.Column(db.Boolean, nullable=False, default=False)
    shuffle_options         = db.Column(db.Boolean, nullable=False, default=False)
    show_results_to_student = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    items      = db.relationship("BundleItem",  back_populates="bundle",
                                 lazy="select", cascade="all, delete-orphan",
                                 order_by="BundleItem.order_index")
    results    = db.relationship("TestResult",  back_populates="bundle",
                                 lazy="dynamic", cascade="all, delete-orphan",
                                 foreign_keys="TestResult.bundle_id")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def tests(self):
        """Return list of Test objects in this bundle."""
        return [item.test for item in self.items]

    @property
    def test_count(self) -> int:
        return len(self.items)

    def is_accessible(self) -> bool:
        """Return True if the bundle is currently open for students."""
        if not self.is_active:
            return False
        now = datetime.now(timezone.utc)
        if self.available_from  and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True

    def regenerate_pin(self) -> str:
        """Generate and save a brand-new PIN code."""
        self.pin_code = _generate_pin()
        return self.pin_code

    def __repr__(self) -> str:
        return f"<TestBundle id={self.id} pin={self.pin_code!r} tests={self.test_count}>"


# ---------------------------------------------------------------------------
# BundleItem  (one test inside a TestBundle)
# ---------------------------------------------------------------------------

class BundleItem(db.Model):
    """
    Links a Test to a TestBundle. Each item represents one test
    within the bundle. The order_index determines display order.
    """
    __tablename__ = "bundle_items"

    id          = db.Column(db.Integer, primary_key=True)
    bundle_id   = db.Column(db.Integer, db.ForeignKey("test_bundles.id"), nullable=False, index=True)
    test_id     = db.Column(db.Integer, db.ForeignKey("tests.id"),        nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    bundle = db.relationship("TestBundle", back_populates="items")
    test   = db.relationship("Test")

    def __repr__(self) -> str:
        return f"<BundleItem id={self.id} bundle_id={self.bundle_id} test_id={self.test_id}>"


# ---------------------------------------------------------------------------
# TestResult  (one student's attempt at an AssignedTest or one test in a Bundle)
# ---------------------------------------------------------------------------

class TestResult(db.Model):
    """
    A single student's attempt at a test.

    Students are anonymous — no user account.  Identity is stored as plain
    text fields supplied by the student before starting the test.

    Results can be linked to:
    - An AssignedTest (single-test PIN) via assigned_test_id
    - A TestBundle (multi-test PIN) via bundle_id

    The test_id always points to the specific Test being answered.
    """
    __tablename__ = "test_results"

    id               = db.Column(db.Integer, primary_key=True)
    assigned_test_id = db.Column(db.Integer, db.ForeignKey("assigned_tests.id"), nullable=True, index=True)
    bundle_id        = db.Column(db.Integer, db.ForeignKey("test_bundles.id"),   nullable=True, index=True)
    test_id          = db.Column(db.Integer, db.ForeignKey("tests.id"),          nullable=False, index=True)

    # ------------------------------------------------------------------
    # Student identity (free text — no account required)
    # ------------------------------------------------------------------
    student_last_name  = db.Column(db.String(128), nullable=False)   # Фамилия
    student_first_name = db.Column(db.String(128), nullable=False)   # Имя
    student_grade      = db.Column(db.String(8),   nullable=False)   # Класс (число), e.g. "10"
    student_letter     = db.Column(db.String(8),   nullable=False)   # Литер, e.g. "А"

    # ------------------------------------------------------------------
    # Attempt metadata
    # ------------------------------------------------------------------
    started_at    = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    submitted_at  = db.Column(db.DateTime(timezone=True), nullable=True)  # None if not yet submitted
    is_completed  = db.Column(db.Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    score         = db.Column(db.Float,   nullable=True)   # raw score (sum of points)
    max_score     = db.Column(db.Float,   nullable=True)   # maximum possible score
    percentage    = db.Column(db.Float,   nullable=True)   # 0–100

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    assigned_test   = db.relationship("AssignedTest", back_populates="results")
    bundle          = db.relationship("TestBundle",   back_populates="results",
                                      foreign_keys=[bundle_id])
    test            = db.relationship("Test")
    answer_details  = db.relationship("ResultAnswer",  back_populates="result",
                                      lazy="dynamic",   cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    @property
    def student_full_name(self) -> str:
        return f"{self.student_last_name} {self.student_first_name}"

    @property
    def student_class(self) -> str:
        """Formatted class string, e.g. '10-А'."""
        return f"{self.student_grade}-{self.student_letter}"

    @property
    def duration_seconds(self) -> Optional[int]:
        """Wall-clock duration of the attempt in seconds."""
        if self.submitted_at and self.started_at:
            return int((self.submitted_at - self.started_at).total_seconds())
        return None

    @property
    def pin_code(self) -> str:
        """Return the PIN code this result belongs to."""
        if self.assigned_test:
            return self.assigned_test.pin_code
        if self.bundle:
            return self.bundle.pin_code
        return "—"

    def calculate_score(self) -> None:
        """
        Recalculate score, max_score and percentage from ResultAnswer rows.
        Call this after all answers have been saved, before marking is_completed.
        """
        answers = self.answer_details.all()
        self.score     = sum(a.points_earned for a in answers)
        self.max_score = sum(a.points_possible for a in answers)
        self.percentage = round((self.score / self.max_score * 100) if self.max_score else 0, 2)

    def __repr__(self) -> str:
        return (f"<TestResult id={self.id} student={self.student_full_name!r} "
                f"score={self.score}/{self.max_score}>")


# ---------------------------------------------------------------------------
# ResultAnswer  (student's answer to ONE question within a TestResult)
# ---------------------------------------------------------------------------

class ResultAnswer(db.Model):
    """
    Stores the student's answer to a single question.

    For SINGLE / MULTIPLE questions: selected option IDs are stored as a
    comma-separated string in `selected_option_ids`.
    For TEXT questions: the typed answer is stored in `text_answer`.
    """
    __tablename__ = "result_answers"

    id          = db.Column(db.Integer, primary_key=True)
    result_id   = db.Column(db.Integer, db.ForeignKey("test_results.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"),    nullable=False, index=True)

    # ------------------------------------------------------------------
    # Student's answer payload
    # ------------------------------------------------------------------
    # For choice questions — comma-separated AnswerOption IDs, e.g. "3,7"
    selected_option_ids = db.Column(db.String(512), nullable=True)
    # For free-text questions
    text_answer         = db.Column(db.Text,        nullable=True)

    # ------------------------------------------------------------------
    # Auto-grading result
    # ------------------------------------------------------------------
    is_correct      = db.Column(db.Boolean, nullable=True)    # None = not yet graded (e.g. text)
    points_earned   = db.Column(db.Float,   nullable=False, default=0.0)
    points_possible = db.Column(db.Float,   nullable=False, default=1.0)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    result   = db.relationship("TestResult", back_populates="answer_details")
    question = db.relationship("Question")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def selected_ids_list(self) -> list:
        """Return selected option IDs as a list of integers."""
        if not self.selected_option_ids:
            return []
        return [int(x) for x in self.selected_option_ids.split(",") if x.strip()]

    @selected_ids_list.setter
    def selected_ids_list(self, ids: list[int]) -> None:
        self.selected_option_ids = ",".join(str(i) for i in ids)

    def __repr__(self) -> str:
        return (f"<ResultAnswer id={self.id} result_id={self.result_id} "
                f"question_id={self.question_id} correct={self.is_correct}>")
