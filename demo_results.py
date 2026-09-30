from academic import get_grade_point
import random
from database import get_connection


# ============================================================
# ACADTWIN DEMO RESULT GENERATOR
# ------------------------------------------------------------
# Adds realistic Semester 3 results to DEMO students.
#
# SAFE:
# - Does NOT delete students
# - Does NOT modify non-DEMO students
# - Only works on roll numbers beginning with DEMO-
# - Replaces existing Semester 3 results only for DEMO students
# ============================================================

SEMESTER = 3

random.seed(42)


def generate_marks(student_number):
    """
    Generates varied but believable student performance.
    """

    # Excellent student
    if student_number % 12 == 0:
        return random.randint(88, 96)

    # Strong student
    elif student_number % 5 == 0:
        return random.randint(78, 89)

    # Average student
    elif student_number % 3 == 0:
        return random.randint(64, 78)

    # Weak / failing profile
    elif student_number % 10 == 1:
        return random.randint(32, 58)

    # Normal student
    else:
        return random.randint(55, 76)


def main():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get DEMO students only
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            roll_no,
            name,
            branch_id

        FROM students

        WHERE roll_no LIKE 'DEMO-%'

        ORDER BY id
    """)

    students = cursor.fetchall()

    if not students:
        print("No DEMO students found.")
        connection.close()
        return

    print()
    print("=" * 65)
    print("        ACADTWIN DEMO RESULT GENERATOR")
    print("=" * 65)
    print()
    print(f"Demo students found: {len(students)}")
    print()

    generated = 0
    passed = 0
    failed = 0

    # --------------------------------------------------------
    # Process every demo student
    # --------------------------------------------------------

    for student_number, student in enumerate(students, start=1):

        student_id = student[0]
        roll_no = student[1]
        name = student[2]
        branch_id = student[3]

        # ----------------------------------------------------
        # Get this student's branch-specific subjects
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                name,
                credits

            FROM subjects

            WHERE branch_id = ?
            AND semester = ?

            ORDER BY id
        """, (
            branch_id,
            SEMESTER
        ))

        subjects = cursor.fetchall()

        if not subjects:
            print(
                f"SKIPPED: {roll_no} - "
                f"No Semester 3 subjects configured."
            )
            continue

        # ----------------------------------------------------
        # Remove OLD Semester 3 result for DEMO student
        # ----------------------------------------------------

        cursor.execute("""
            DELETE FROM results

            WHERE student_id = ?
            AND semester = ?
        """, (
            student_id,
            SEMESTER
        ))

        cursor.execute("""
            DELETE FROM semester_results

            WHERE student_id = ?
            AND semester = ?
        """, (
            student_id,
            SEMESTER
        ))

        total_marks = 0
        total_weighted_points = 0
        total_credits = 0

        student_failed = False

        # ----------------------------------------------------
        # Generate marks for every subject
        # ----------------------------------------------------

        for subject_index, subject in enumerate(subjects):

            subject_id = subject[0]
            credits = subject[2]

            marks = generate_marks(student_number)

            # Make selected students fail ONE subject
            # while keeping other subjects believable.
            if (
                student_number % 10 == 1
                and subject_index == 1
            ):
                marks = random.randint(28, 38)

            grade_point, grade = get_grade_point(marks)

            if marks < 40:
                student_failed = True

            total_marks += marks

            total_weighted_points += (
                grade_point * credits
            )

            total_credits += credits

            cursor.execute("""
                INSERT INTO results (
                    student_id,
                    subject_id,
                    semester,
                    marks,
                    grade,
                    grade_point
                )

                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                student_id,
                subject_id,
                SEMESTER,
                marks,
                grade,
                grade_point
            ))

        # ----------------------------------------------------
        # Calculate semester result
        # ----------------------------------------------------

        percentage = (
            total_marks / len(subjects)
        )

        sgpa = (
            total_weighted_points / total_credits
            if total_credits
            else 0
        )

        result_status = (
            "FAIL"
            if student_failed
            else "PASS"
        )

        cursor.execute("""
            INSERT INTO semester_results (
                student_id,
                semester,
                sgpa,
                percentage,
                result
            )

            VALUES (?, ?, ?, ?, ?)
        """, (
            student_id,
            SEMESTER,
            round(sgpa, 2),
            round(percentage, 2),
            result_status
        ))

        generated += 1

        if result_status == "PASS":
            passed += 1
        else:
            failed += 1

        print(
            f"{roll_no:<18} "
            f"{name[:22]:<22} "
            f"SGPA {sgpa:.2f}   "
            f"{percentage:.1f}%   "
            f"{result_status}"
        )

    # --------------------------------------------------------
    # Save everything
    # --------------------------------------------------------

    connection.commit()
    connection.close()

    print()
    print("=" * 65)
    print("RESULT GENERATION COMPLETE")
    print("=" * 65)
    print(f"Students processed : {generated}")
    print(f"Passed             : {passed}")
    print(f"Failed             : {failed}")
    print()
    print("Original/non-DEMO students were NOT modified.")
    print("=" * 65)


if __name__ == "__main__":
    main()