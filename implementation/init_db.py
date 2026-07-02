"""Initialize SQLite database with schema and seed data."""

from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "lab.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cohort TEXT NOT NULL,
    score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    grade REAL,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
"""

SEED_SQL = """
INSERT INTO students (name, cohort, score) VALUES
    ('Alice Nguyen', 'A1', 92.5),
    ('Bob Tran', 'A1', 78.0),
    ('Carol Le', 'B2', 88.5),
    ('David Pham', 'B2', 71.0),
    ('Eva Hoang', 'A1', 95.0);

INSERT INTO courses (title, credits) VALUES
    ('Database Systems', 3),
    ('Python Programming', 4),
    ('Machine Learning', 3);

INSERT INTO enrollments (student_id, course_id, grade) VALUES
    (1, 1, 90.0),
    (1, 2, 94.0),
    (2, 1, 75.0),
    (3, 3, 89.0),
    (5, 2, 97.0);
"""


def create_database(db_path: Path | None = None) -> Path:
    """Create database file, apply schema, and insert seed rows."""
    import sqlite3

    path = db_path or DB_PATH
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()

    return path


if __name__ == "__main__":
    db = create_database()
    print(f"Database created at: {db}")
