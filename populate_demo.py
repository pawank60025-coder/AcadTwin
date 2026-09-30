from academic import get_grade_point
import random

from database import get_connection, create_database


# ============================================================
# ACADTWIN SEMESTER 3 DEMO DATA GENERATOR
# ============================================================

SEMESTER = 3
BATCH = "2025-2029"

random.seed(42)


# ------------------------------------------------------------
# Prototype Semester 3 Academic Configuration
#
# These are DEMO configurations for the prototype.
# They should not be presented as official AKTU mappings.
# ------------------------------------------------------------

ACADEMIC_CONFIG = {

    "Computer Science & Engineering": {
        "prefix": "CSE",

        "subjects": [
            ("DSTL", "Discrete Structures", 3),
            ("DS", "Data Structures", 4),
            ("PY", "Python Programming", 2),
            ("DE", "Digital Electronics", 4),
            ("COA", "Computer Organization & Architecture", 4),
            ("TC", "Technical Communication", 3),
        ],
    },

    "CSE (AI & ML)": {
        "prefix": "AIML",

        "subjects": [
            ("DSTL", "Discrete Structures", 3),
            ("DS", "Data Structures", 4),
            ("PY", "Python Programming", 2),
            ("AIF", "AI Fundamentals", 4),
            ("COA", "Computer Organization & Architecture", 4),
            ("TC", "Technical Communication", 3),
        ],
    },

    "Electronics & Communication Engineering": {
        "prefix": "ECE",

        "subjects": [
            ("EM3", "Engineering Mathematics III", 3),
            ("EDC", "Electronic Devices & Circuits", 4),
            ("DSD", "Digital System Design", 4),
            ("SS", "Signals & Systems", 3),
            ("NA", "Network Analysis", 3),
            ("TC", "Technical Communication", 3),
        ],
    },
}


# ------------------------------------------------------------
# Demo Student Names
# ------------------------------------------------------------

STUDENT_NAMES = [
    "Aarav Sharma",
    "Aditi Singh",
    "Akash Verma",
    "Ananya Gupta",
    "Arjun Yadav",
    "Ayush Mishra",
    "Dev Kumar",
    "Diya Sharma",

    "Gaurav Singh",
    "Harsh Verma",
    "Isha Gupta",
    "Karan Yadav",
    "Khushi Mishra",
    "Krishna Kumar",
    "Mehak Sharma",
    "Mohit Singh",

    "Nandini Verma",
    "Nikhil Gupta",
    "Palak Yadav",
    "Pranav Mishra",
    "Priya Kumar",
    "Rahul Sharma",
    "Riya Singh",
    "Rohan Verma",

    "Sakshi Gupta",
    "Sameer Yadav",
    "Sanya Mishra",
    "Shivam Kumar",
    "Shreya Sharma",
    "Siddharth Singh",
    "Simran Verma",
    "Tanmay Gupta",

    "Tanya Yadav",
    "Utkarsh Mishra",
    "Vaishnavi Kumar",
    "Varun Sharma",
    "Yash Singh",
    "Yuvraj Verma",
    "Neha Gupta",
    "Aditya Yadav",

    "Anjali Mishra",
    "Aryan Kumar",
    "Deepak Sharma",
    "Kavya Singh",
    "Manish Verma",
    "Muskan Gupta",
    "Nitin Yadav",
    "Pooja Mishra",
]


# ============================================================
# PERFORMANCE PROFILE
# ============================================================

def generate_marks(student_number):
    """
    Generates controlled demo performance.

    This creates:
    - excellent students
    - strong students
    - average students
    - weaker students
    - occasional failing students
    """

    profile = student_number % 10

    # Excellent
    if profile == 0:
        low, high = 88, 97

    # Strong
    elif profile in (1, 2):
        low, high = 78, 91

    # Above average
    elif profile in (3, 4, 5):
        low, high = 68, 84

    # Average
    elif profile in (6, 7):
        low, high = 55, 74

    # Weak
    elif profile == 8:
        low, high = 42, 63

    # Student with possibility of failure
    else:
        low, high = 35, 58

    marks = [
        random.randint(low, high)
        for _ in range(6)
    ]

    # Ensure the failure profile actually contains
    # at least one failed subject.
    if profile == 9:
        failed_subject = random.randint(0, 5)
        marks[failed_subject] = random.randint(28, 38)

    return marks


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_or_create_course(cursor):

    cursor.execute(
        "SELECT id FROM courses WHERE name = ?",
        ("B.Tech",)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO courses (name) VALUES (?)",
        ("B.Tech",)
    )

    return cursor.lastrowid


def get_or_create_branch(cursor, course_id, branch_name):

    cursor.execute(
        """
        SELECT id
        FROM branches
        WHERE course_id = ?
        AND name = ?
        """,
        (course_id, branch_name)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO branches (
            course_id,
            name
        )
        VALUES (?, ?)
        """,
        (
            course_id,
            branch_name
        )
    )

    return cursor.lastrowid


def get_or_create_section(
    cursor,
    branch_id,
    section_name
):

    cursor.execute(
        """
        SELECT id
        FROM sections
        WHERE branch_id = ?
        AND semester = ?
        AND name = ?
        """,
        (
            branch_id,
            SEMESTER,
            section_name
        )
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO sections (
            branch_id,
            semester,
            name
        )
        VALUES (?, ?, ?)
        """,
        (
            branch_id,
            SEMESTER,
            section_name
        )
    )

    return cursor.lastrowid


def get_or_create_subject(
    cursor,
    branch_id,
    code,
    name,
    credits
):

    cursor.execute(
        """
        SELECT id
        FROM subjects
        WHERE branch_id = ?
        AND semester = ?
        AND name = ?
        """,
        (
            branch_id,
            SEMESTER,
            name
        )
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO subjects (
            code,
            name,
            branch_id,
            semester,
            credits
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            code,
            name,
            branch_id,
            SEMESTER,
            credits
        )
    )

    return cursor.lastrowid


# ============================================================
# REMOVE OLD GENERATED DEMO STUDENTS
# ============================================================

def remove_old_demo_students(cursor):
    """
    Makes this script safe to rerun.

    Generated roll numbers use:
    DEMO-CSE-...
    DEMO-AIML-...
    DEMO-ECE-...

    Existing non-DEMO records are preserved.
    """

    cursor.execute(
        """
        SELECT id
        FROM students
        WHERE roll_no LIKE 'DEMO-%'
        """
    )

    demo_students = cursor.fetchall()

    for row in demo_students:

        student_id = row[0]

        cursor.execute(
            """
            DELETE FROM results
            WHERE student_id = ?
            """,
            (student_id,)
        )

        cursor.execute(
            """
            DELETE FROM semester_results
            WHERE student_id = ?
            """,
            (student_id,)
        )

        cursor.execute(
            """
            DELETE FROM students
            WHERE id = ?
            """,
            (student_id,)
        )


# ============================================================
# CREATE STUDENT
# ============================================================

def create_student(
    cursor,
    roll_no,
    name,
    course_id,
    branch_id,
    section_id
):

    cursor.execute(
        """
        INSERT INTO students (
            roll_no,
            name,
            course_id,
            branch_id,
            section_id,
            batch
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            roll_no,
            name,
            course_id,
            branch_id,
            section_id,
            BATCH
        )
    )

    return cursor.lastrowid


# ============================================================
# CREATE RESULT
# ============================================================

def create_result(
    cursor,
    student_id,
    subject_ids,
    subject_config,
    marks_list
):

    total_marks = 0
    total_weighted_points = 0
    total_credits = 0

    failed = False

    for index, subject_id in enumerate(subject_ids):

        marks = marks_list[index]

        code, subject_name, credits = subject_config[index]

        grade_point, grade = get_grade_point(marks)

        total_marks += marks

        total_weighted_points += (
            grade_point * credits
        )

        total_credits += credits

        if marks < 40:
            failed = True

        cursor.execute(
            """
            INSERT INTO results (
                student_id,
                subject_id,
                semester,
                marks,
                grade,
                grade_point
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                student_id,
                subject_id,
                SEMESTER,
                marks,
                grade,
                grade_point
            )
        )

    percentage = total_marks / len(subject_ids)

    if total_credits > 0:
        sgpa = (
            total_weighted_points
            / total_credits
        )
    else:
        sgpa = 0

    result_status = (
        "FAIL"
        if failed
        else "PASS"
    )

    cursor.execute(
        """
        INSERT INTO semester_results (
            student_id,
            semester,
            sgpa,
            percentage,
            result
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            student_id,
            SEMESTER,
            round(sgpa, 2),
            round(percentage, 2),
            result_status
        )
    )


# ============================================================
# MAIN DEMO GENERATOR
# ============================================================

def populate_demo():

    # Make sure database tables exist.
    create_database()

    connection = get_connection()

    cursor = connection.cursor()

    try:

        print()
        print("=" * 60)
        print("ACADTWIN DEMO DATA GENERATOR")
        print("=" * 60)

        # ----------------------------------------------------
        # Remove previously generated demo students
        # ----------------------------------------------------

        remove_old_demo_students(cursor)

        print(
            "Old generated demo records cleared."
        )

        # ----------------------------------------------------
        # Course
        # ----------------------------------------------------

        course_id = get_or_create_course(cursor)

        # ----------------------------------------------------
        # Student counter
        # ----------------------------------------------------

        name_index = 0
        generated_students = 0
        generated_results = 0

        # ----------------------------------------------------
        # Generate branch data
        # ----------------------------------------------------

        for branch_name, config in ACADEMIC_CONFIG.items():

            branch_id = get_or_create_branch(
                cursor,
                course_id,
                branch_name
            )

            prefix = config["prefix"]

            subjects = config["subjects"]

            # ------------------------------------------------
            # Create branch-specific subjects
            # ------------------------------------------------

            subject_ids = []

            for code, subject_name, credits in subjects:

                subject_id = get_or_create_subject(
                    cursor,
                    branch_id,
                    code,
                    subject_name,
                    credits
                )

                subject_ids.append(subject_id)

            # ------------------------------------------------
            # Sections A and B
            # ------------------------------------------------

            for section_name in ["A", "B"]:

                section_id = get_or_create_section(
                    cursor,
                    branch_id,
                    section_name
                )

                # --------------------------------------------
                # 8 students per section
                # --------------------------------------------

                for student_position in range(1, 9):

                    name = STUDENT_NAMES[name_index]

                    name_index += 1

                    roll_no = (
                        f"DEMO-{prefix}-"
                        f"{section_name}-"
                        f"{student_position:02d}"
                    )

                    student_id = create_student(
                        cursor,
                        roll_no,
                        name,
                        course_id,
                        branch_id,
                        section_id
                    )

                    generated_students += 1

                    marks = generate_marks(
                        generated_students
                    )

                    create_result(
                        cursor,
                        student_id,
                        subject_ids,
                        subjects,
                        marks
                    )

                    generated_results += 1

        # ----------------------------------------------------
        # Save everything
        # ----------------------------------------------------

        connection.commit()

        print()
        print("Demo generation completed successfully.")
        print()
        print(
            f"Students generated : "
            f"{generated_students}"
        )

        print(
            f"Results generated  : "
            f"{generated_results}"
        )

        print(
            f"Branches           : "
            f"{len(ACADEMIC_CONFIG)}"
        )

        print(
            "Sections           : 6"
        )

        print(
            f"Semester           : "
            f"{SEMESTER}"
        )

        print()
        print("=" * 60)

    except Exception as error:

        connection.rollback()

        print()
        print("ERROR:")
        print(error)
        print()
        print(
            "No demo changes were committed."
        )

    finally:

        connection.close()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    populate_demo()
