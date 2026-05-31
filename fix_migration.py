"""Drop old student_class column since it's replaced by student_grade + student_letter."""
from app import create_app
from models import db

app = create_app()

SQL = """
-- Drop the old student_class column entirely
ALTER TABLE test_results DROP COLUMN IF EXISTS student_class;
"""

with app.app_context():
    print("Dropping student_class column...")
    with db.engine.connect() as conn:
        conn.execute(db.text(SQL))
        conn.commit()
    print("✅ Column dropped!")
