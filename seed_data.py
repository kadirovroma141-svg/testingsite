"""Seed script: creates admin, two teachers, and sample tests."""
from app import create_app
from models import db, User, Test, Question, AnswerOption, UserRole, QuestionType, TestCreationMethod

app = create_app()

with app.app_context():
    # Check if already seeded
    if User.query.filter_by(username="admin").first():
        print("⚠️  Already seeded. Skipping.")
        exit(0)

    # --- Admin ---
    admin = User(username="admin", email="admin@school.ru",
                 full_name="Администратор Школы", role=UserRole.ADMIN)
    admin.set_password("admin123")
    db.session.add(admin)

    # --- Teacher 1: Math ---
    t1 = User(username="math_teacher", email="math@school.ru",
              full_name="Иванова Мария", role=UserRole.TEACHER)
    t1.set_password("teacher123")
    db.session.add(t1)

    # --- Teacher 2: Physics ---
    t2 = User(username="physics_teacher", email="physics@school.ru",
              full_name="Петров Алексей", role=UserRole.TEACHER)
    t2.set_password("teacher123")
    db.session.add(t2)

    db.session.flush()

    # --- Math test ---
    math_test = Test(author_id=t1.id, title="Квадратные уравнения",
                     subject="Математика", grade_level="10",
                     creation_method=TestCreationMethod.MANUAL, is_draft=False)
    db.session.add(math_test)
    db.session.flush()

    q1 = Question(test_id=math_test.id, order_index=0,
                  question_type=QuestionType.SINGLE,
                  text="Сколько корней имеет уравнение x² - 4 = 0?",
                  points=1.0)
    db.session.add(q1)
    db.session.flush()
    for i, (txt, correct) in enumerate([("0", False), ("1", False), ("2", True), ("3", False)]):
        db.session.add(AnswerOption(question_id=q1.id, order_index=i, text=txt, is_correct=correct))

    q2 = Question(test_id=math_test.id, order_index=1,
                  question_type=QuestionType.SINGLE,
                  text="Чему равен дискриминант уравнения x² + 2x + 1 = 0?",
                  points=1.0)
    db.session.add(q2)
    db.session.flush()
    for i, (txt, correct) in enumerate([("-4", False), ("0", True), ("4", False), ("8", False)]):
        db.session.add(AnswerOption(question_id=q2.id, order_index=i, text=txt, is_correct=correct))

    # --- Physics test ---
    phys_test = Test(author_id=t2.id, title="Законы Ньютона",
                     subject="Физика", grade_level="10",
                     creation_method=TestCreationMethod.MANUAL, is_draft=False)
    db.session.add(phys_test)
    db.session.flush()

    q3 = Question(test_id=phys_test.id, order_index=0,
                  question_type=QuestionType.SINGLE,
                  text="Формулировка какого закона: «Тело остаётся в покое или движется прямолинейно и равномерно, если на него не действуют силы»?",
                  points=1.0)
    db.session.add(q3)
    db.session.flush()
    for i, (txt, correct) in enumerate([("Первый закон Ньютона", True), ("Второй закон Ньютона", False),
                                         ("Третий закон Ньютона", False), ("Закон Гука", False)]):
        db.session.add(AnswerOption(question_id=q3.id, order_index=i, text=txt, is_correct=correct))

    q4 = Question(test_id=phys_test.id, order_index=1,
                  question_type=QuestionType.SINGLE,
                  text="Единица измерения силы в СИ?",
                  points=1.0)
    db.session.add(q4)
    db.session.flush()
    for i, (txt, correct) in enumerate([("Джоуль", False), ("Ньютон", True), ("Паскаль", False), ("Ватт", False)]):
        db.session.add(AnswerOption(question_id=q4.id, order_index=i, text=txt, is_correct=correct))

    db.session.commit()
    print("✅ Seed complete!")
    print(f"   Admin: admin@school.ru / admin123")
    print(f"   Teacher 1 (Math): math@school.ru / teacher123")
    print(f"   Teacher 2 (Physics): physics@school.ru / teacher123")
