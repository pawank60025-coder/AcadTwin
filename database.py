import sqlite3
from pathlib import Path

DB_NAME = str(Path(__file__).with_name("acadtwin.db"))


def get_connection():
    return sqlite3.connect(DB_NAME)


def create_database():
    connection = get_connection()
    cursor = connection.cursor()

    # COURSES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    # BRANCHES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    """)

    # SECTIONS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            semester INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        )
    """)

    # STUDENTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT UNIQUE,
            name TEXT NOT NULL,
            course_id INTEGER,
            branch_id INTEGER,
            section_id INTEGER,
            batch TEXT,

            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (branch_id) REFERENCES branches(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
        )
    """)

    # SUBJECTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT NOT NULL,
            branch_id INTEGER,
            semester INTEGER NOT NULL,
            credits INTEGER NOT NULL,

            FOREIGN KEY (branch_id) REFERENCES branches(id)
        )
    """)

    # RESULTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            semester INTEGER NOT NULL,
            marks INTEGER,
            grade TEXT,
            grade_point REAL,

            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    # SEMESTER RESULTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semester_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            semester INTEGER NOT NULL,
            sgpa REAL,
            percentage REAL,
            result TEXT,

            FOREIGN KEY (student_id) REFERENCES students(id),

            UNIQUE(student_id, semester)
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_database()
    print("AcadTwin database created successfully.")
