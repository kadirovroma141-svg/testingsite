"""
Migration script: Add TestBundle, BundleItem tables and update TestResult.
Run this once to migrate the existing PostgreSQL database.
"""
from app import create_app
from models import db

app = create_app()

MIGRATION_SQL = """
-- ============================================================
-- 1. Create test_bundles table
-- ============================================================
CREATE TABLE IF NOT EXISTS test_bundles (
    id SERIAL PRIMARY KEY,
    pin_code VARCHAR(16) UNIQUE NOT NULL,
    label VARCHAR(256),
    created_by_id INTEGER NOT NULL REFERENCES users(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    available_from TIMESTAMP WITH TIME ZONE,
    available_until TIMESTAMP WITH TIME ZONE,
    time_limit_minutes INTEGER,
    max_attempts INTEGER DEFAULT 1,
    shuffle_questions BOOLEAN NOT NULL DEFAULT FALSE,
    shuffle_options BOOLEAN NOT NULL DEFAULT FALSE,
    show_results_to_student BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_test_bundles_pin_code ON test_bundles(pin_code);
CREATE INDEX IF NOT EXISTS ix_test_bundles_created_by_id ON test_bundles(created_by_id);

-- ============================================================
-- 2. Create bundle_items table
-- ============================================================
CREATE TABLE IF NOT EXISTS bundle_items (
    id SERIAL PRIMARY KEY,
    bundle_id INTEGER NOT NULL REFERENCES test_bundles(id) ON DELETE CASCADE,
    test_id INTEGER NOT NULL REFERENCES tests(id),
    order_index INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_bundle_items_bundle_id ON bundle_items(bundle_id);
CREATE INDEX IF NOT EXISTS ix_bundle_items_test_id ON bundle_items(test_id);

-- ============================================================
-- 3. Add new columns to test_results
-- ============================================================

-- Add test_id column (nullable first, we'll populate then make NOT NULL)
DO $$ BEGIN
    ALTER TABLE test_results ADD COLUMN test_id INTEGER REFERENCES tests(id);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add bundle_id column
DO $$ BEGIN
    ALTER TABLE test_results ADD COLUMN bundle_id INTEGER REFERENCES test_bundles(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add student_grade column
DO $$ BEGIN
    ALTER TABLE test_results ADD COLUMN student_grade VARCHAR(8);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add student_letter column
DO $$ BEGIN
    ALTER TABLE test_results ADD COLUMN student_letter VARCHAR(8);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- ============================================================
-- 4. Migrate existing data: populate test_id from assigned_tests
-- ============================================================
UPDATE test_results
SET test_id = assigned_tests.test_id
FROM assigned_tests
WHERE test_results.assigned_test_id = assigned_tests.id
  AND test_results.test_id IS NULL;

-- ============================================================
-- 5. Migrate student_class → student_grade + student_letter
-- ============================================================
-- Try to split "10-А" format into grade="10", letter="А"
UPDATE test_results
SET student_grade = SPLIT_PART(student_class, '-', 1),
    student_letter = SPLIT_PART(student_class, '-', 2)
WHERE student_grade IS NULL AND student_class IS NOT NULL AND student_class LIKE '%-%';

-- For values without dash, put everything in grade
UPDATE test_results
SET student_grade = student_class,
    student_letter = ''
WHERE student_grade IS NULL AND student_class IS NOT NULL AND student_class NOT LIKE '%-%';

-- Default empty for any remaining NULLs
UPDATE test_results SET student_grade = '' WHERE student_grade IS NULL;
UPDATE test_results SET student_letter = '' WHERE student_letter IS NULL;

-- ============================================================
-- 6. Make test_id NOT NULL (after populating)
-- ============================================================
-- First handle any orphaned rows
UPDATE test_results
SET test_id = (SELECT test_id FROM assigned_tests WHERE assigned_tests.id = test_results.assigned_test_id)
WHERE test_id IS NULL AND assigned_test_id IS NOT NULL;

ALTER TABLE test_results ALTER COLUMN test_id SET NOT NULL;
ALTER TABLE test_results ALTER COLUMN student_grade SET NOT NULL;
ALTER TABLE test_results ALTER COLUMN student_letter SET NOT NULL;

-- ============================================================
-- 7. Make assigned_test_id nullable (for bundle results)
-- ============================================================
ALTER TABLE test_results ALTER COLUMN assigned_test_id DROP NOT NULL;

-- ============================================================
-- 8. Create indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_test_results_test_id ON test_results(test_id);
CREATE INDEX IF NOT EXISTS ix_test_results_bundle_id ON test_results(bundle_id);
"""

with app.app_context():
    print("Running migration...")
    with db.engine.connect() as conn:
        conn.execute(db.text(MIGRATION_SQL))
        conn.commit()
    print("✅ Migration complete!")
