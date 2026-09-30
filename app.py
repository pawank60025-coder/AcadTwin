import os
import sqlite3
from contextlib import closing

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from database import create_database, get_connection
from academic import (get_grade_point, calculate_performance, risk_level,
                      solve_target, recommendations)

app = Flask(__name__)
app.secret_key = os.environ.get("ACADTWIN_SECRET_KEY") or os.urandom(32)

create_database()


# ============================================================
# HELPERS
# ============================================================

def rows_to_dicts(cursor, rows):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def row_to_dict(cursor, row):
    if row is None:
        return None

    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def query(connection, sql, parameters=()):
    cursor = connection.execute(sql, parameters)
    return rows_to_dicts(cursor, cursor.fetchall())


def selected_semester():
    value = request.values.get("semester", "3")
    try:
        semester = int(value)
    except (ValueError, TypeError):
        abort(400, description="Choose a valid semester from 1 to 8.")
    if not 1 <= semester <= 8:
        abort(400, description="Choose a valid semester from 1 to 8.")
    return semester


def student_record(connection, student_id):
    rows = query(connection, """
        SELECT st.*, c.name AS course_name, b.name AS branch_name,
               sec.name AS section_name, sec.semester
        FROM students st
        LEFT JOIN courses c ON st.course_id = c.id
        LEFT JOIN branches b ON st.branch_id = b.id
        LEFT JOIN sections sec ON st.section_id = sec.id
        WHERE st.id = ?
    """, (student_id,))
    if not rows:
        abort(404, description="This student record could not be found.")
    return rows[0]


def result_subjects(connection, student_id, semester):
    return query(connection, """
        SELECT sub.id, sub.name, sub.code, sub.credits, r.marks,
               r.grade, r.grade_point, r.semester,
               sub.name AS subject_name, sub.code AS subject_code
        FROM results r JOIN subjects sub ON sub.id = r.subject_id
        WHERE r.student_id = ? AND r.semester = ? ORDER BY sub.id
    """, (student_id, semester))


def parse_marks(value):
    try:
        marks = int(value)
    except (TypeError, ValueError):
        raise ValueError("Enter a whole-number mark from 0 to 100 for every subject.")
    if not 0 <= marks <= 100:
        raise ValueError("Marks must be between 0 and 100. Your stored results are unchanged.")
    return marks


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def home():
    return overview()


@app.route("/students")
def student_records():
    return overview(records_only=True)


@app.route("/digital-twin")
def twin_directory():
    return overview(twin_mode=True)


def overview(records_only=False, twin_mode=False):
    semester = selected_semester()
    branch_id = request.args.get("branch_id", type=int)
    section_id = request.args.get("section_id", type=int)
    course_id = request.args.get("course_id", type=int)
    search = request.args.get("q", "").strip()
    conditions, parameters = [], [semester]
    for column, value in (("branch_id", branch_id), ("section_id", section_id),
                          ("course_id", course_id)):
        if value is not None:
            conditions.append(f"st.{column} = ?")
            parameters.append(value)
    if search:
        conditions.append("(st.name LIKE ? OR st.roll_no LIKE ?)")
        parameters.extend([f"%{search}%", f"%{search}%"])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with closing(get_connection()) as connection:
        students = query(connection, f"""
            SELECT st.id, st.roll_no, st.name, st.batch, st.branch_id,
                   st.course_id, st.section_id, c.name AS course_name,
                   b.name AS branch_name, sec.name AS section_name, sec.semester,
                   sr.sgpa, sr.percentage, sr.result,
                   (SELECT MIN(r.marks) FROM results r
                    WHERE r.student_id = st.id AND r.semester = sr.semester) AS min_marks
            FROM students st
            LEFT JOIN courses c ON st.course_id = c.id
            LEFT JOIN branches b ON st.branch_id = b.id
            LEFT JOIN sections sec ON st.section_id = sec.id
            LEFT JOIN semester_results sr ON sr.student_id = st.id AND sr.semester = ?
            {where} ORDER BY st.name, st.id
        """, parameters)
        courses = query(connection, "SELECT * FROM courses ORDER BY name")
        branches = query(connection, "SELECT * FROM branches ORDER BY name")
        registration_sections = query(connection, "SELECT id, branch_id, semester, name FROM sections ORDER BY semester, name")
        sections = query(connection, """
            SELECT sec.*, b.name AS branch_name FROM sections sec
            JOIN branches b ON b.id = sec.branch_id
            WHERE sec.semester = ? AND (? IS NULL OR sec.branch_id = ?)
            ORDER BY b.name, sec.name
        """, (semester, branch_id, branch_id))
    recorded = [s for s in students if s["sgpa"] is not None]
    for student in students:
        state = None if student["sgpa"] is None else {
            "sgpa": student["sgpa"], "result": student["result"],
            "subjects": [{"marks": student["min_marks"]}] if student["min_marks"] is not None else []
        }
        student["risk"] = risk_level(state)
    total_results = len(recorded)
    passed_count = sum(s["result"] == "PASS" for s in recorded)
    failed_count = sum(s["result"] == "FAIL" for s in recorded)
    avg_sgpa = sum(s["sgpa"] for s in recorded) / total_results if total_results else 0
    class_average = sum(s["percentage"] for s in recorded) / total_results if total_results else 0
    top_performer = max(recorded, key=lambda s: (s["sgpa"], s["percentage"]), default=None)
    groups = {}
    for student in recorded:
        groups.setdefault(student["branch_name"] or "Unassigned", []).append(student["sgpa"])
    branch_performance = [{"branch_name": name, "avg_sgpa": round(sum(values) / len(values), 2)}
                          for name, values in sorted(groups.items())]
    strongest_branch = max(branch_performance, key=lambda b: b["avg_sgpa"], default=None)
    bins = [0] * 6
    for student in recorded:
        sgpa = student["sgpa"]
        bins[0 if sgpa < 5 else min(5, int(sgpa) - 4)] += 1
    chart_data = {
        "branch": {"labels": [b["branch_name"] for b in branch_performance],
                   "values": [b["avg_sgpa"] for b in branch_performance]},
        "result": {"labels": ["PASS", "FAIL"], "values": [passed_count, failed_count]},
        "sgpa": {"labels": ["<5", "5-<6", "6-<7", "7-<8", "8-<9", "9-10"], "values": bins}
    }
    return render_template(
        "index.html", students=students, total_students=len(students),
        total_results=total_results, avg_sgpa=avg_sgpa, class_average=class_average,
        pass_rate=100 * passed_count / total_results if total_results else 0,
        passed_count=passed_count, failed_count=failed_count,
        at_risk_count=sum(s["risk"]["level"] in ("high", "moderate") for s in recorded),
        top_performer=top_performer, strongest_branch=strongest_branch,
        courses=courses, branches=branches, sections=sections, chart_data=chart_data,
        registration_sections=registration_sections,
        selected_branch_id=branch_id, selected_section_id=section_id,
        selected_course_id=course_id, selected_semester=semester, q=search,
        records_only=records_only, twin_mode=twin_mode
    )

@app.route("/analytics")
def analytics():

    semester = selected_semester()
    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    branch_id = request.args.get(
        "branch_id",
        type=int
    )

    section_id = request.args.get(
        "section_id",
        type=int
    )

    # --------------------------------------------------------
    # BRANCH LIST
    # --------------------------------------------------------

    cursor.execute("""
        SELECT id, name
        FROM branches
        ORDER BY name
    """)

    branches = rows_to_dicts(
        cursor,
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    if branch_id:

        cursor.execute("""
            SELECT sec.id, sec.name, b.name AS branch_name
            FROM sections sec JOIN branches b ON b.id = sec.branch_id
            WHERE sec.branch_id = ?
            AND sec.semester = ?
            ORDER BY sec.name
        """, (branch_id, semester))

    else:

        cursor.execute("""
            SELECT sec.id, sec.name, b.name AS branch_name
            FROM sections sec JOIN branches b ON b.id = sec.branch_id
            WHERE sec.semester = ?
            ORDER BY b.name, sec.name
        """, (semester,))

    sections = rows_to_dicts(
        cursor,
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # DYNAMIC FILTER CONDITIONS
    # --------------------------------------------------------

    conditions = [
        "sr.semester = ?"
    ]

    parameters = [semester]

    if branch_id:

        conditions.append(
            "st.branch_id = ?"
        )

        parameters.append(branch_id)

    if section_id:

        conditions.append(
            "st.section_id = ?"
        )

        parameters.append(section_id)

    where_clause = (
        " WHERE "
        + " AND ".join(conditions)
    )

    # --------------------------------------------------------
    # MAIN METRICS
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            COUNT(*) AS total_results,

            AVG(sr.sgpa) AS avg_sgpa,

            AVG(sr.percentage)
                AS class_average,

            SUM(
                CASE
                    WHEN sr.result = 'PASS'
                    THEN 1
                    ELSE 0
                END
            ) AS passed_count,

            SUM(
                CASE
                    WHEN sr.result = 'FAIL'
                    THEN 1
                    ELSE 0
                END
            ) AS failed_count

        FROM semester_results sr

        JOIN students st
            ON sr.student_id = st.id

        {where_clause}
        """,
        parameters
    )

    metrics = cursor.fetchone()

    total_results = metrics[0] or 0
    avg_sgpa = metrics[1] or 0
    class_average = metrics[2] or 0
    passed_count = metrics[3] or 0
    failed_count = metrics[4] or 0

    pass_rate = (
        (passed_count / total_results) * 100
        if total_results
        else 0
    )

    # --------------------------------------------------------
    # TOP PERFORMER
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            st.id,
            st.roll_no,
            st.name,
            sr.semester,
            sr.sgpa,
            sr.percentage

        FROM semester_results sr

        JOIN students st
            ON sr.student_id = st.id

        {where_clause}

        ORDER BY
            sr.sgpa DESC,
            sr.percentage DESC

        LIMIT 1
        """,
        parameters
    )

    top_performer = row_to_dict(
        cursor,
        cursor.fetchone()
    )

    # --------------------------------------------------------
    # STUDENT PERFORMANCE
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            st.id,
            st.roll_no,
            st.name,

            COUNT(sr.id)
                AS semesters_recorded,

            AVG(sr.sgpa)
                AS average_sgpa,

            AVG(sr.percentage)
                AS average_percentage

        FROM students st

        JOIN semester_results sr
            ON st.id = sr.student_id

        {where_clause}

        GROUP BY
            st.id,
            st.roll_no,
            st.name

        ORDER BY
            average_sgpa DESC,
            average_percentage DESC
        """,
        parameters
    )

    student_performance = rows_to_dicts(
        cursor,
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # SUBJECT PERFORMANCE
    #
    # IMPORTANT:
    # Subject analytics are displayed ONLY when a branch
    # has been selected.
    # --------------------------------------------------------

    subject_performance = []

    highest_subject = None
    lowest_subject = None

    if branch_id:

        subject_conditions = [
            "r.semester = ?",
            "st.branch_id = ?",
            "(sub.branch_id = ? OR sub.branch_id IS NULL)"
        ]

        subject_parameters = [
            semester,
            branch_id,
            branch_id
        ]

        if section_id:

            subject_conditions.append(
                "st.section_id = ?"
            )

            subject_parameters.append(
                section_id
            )

        subject_where = (
            " WHERE "
            + " AND ".join(
                subject_conditions
            )
        )

        cursor.execute(
            f"""
            SELECT
                sub.name
                    AS subject_name,

                AVG(r.marks)
                    AS average_marks,

                MAX(r.marks)
                    AS highest_marks,

                MIN(r.marks)
                    AS lowest_marks

            FROM results r

            JOIN students st
                ON r.student_id = st.id

            JOIN subjects sub
                ON r.subject_id = sub.id

            {subject_where}

            GROUP BY sub.name

            ORDER BY
                average_marks DESC
            """,
            subject_parameters
        )

        subject_performance = rows_to_dicts(
            cursor,
            cursor.fetchall()
        )

        if subject_performance:

            highest_subject = (
                subject_performance[0]
            )

            lowest_subject = min(
                subject_performance,
                key=lambda item:
                    item["average_marks"]
            )

    # --------------------------------------------------------
    # SEMESTER PERFORMANCE
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            sr.semester,

            AVG(sr.sgpa)
                AS average_sgpa,

            AVG(sr.percentage)
                AS average_percentage

        FROM semester_results sr

        JOIN students st
            ON sr.student_id = st.id

        {where_clause}

        GROUP BY
            sr.semester

        ORDER BY
            sr.semester
        """,
        parameters
    )

    semester_performance = rows_to_dicts(
        cursor,
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # SELECTED BRANCH
    # --------------------------------------------------------

    selected_branch = None

    if branch_id:

        cursor.execute("""
            SELECT id, name
            FROM branches
            WHERE id = ?
        """, (branch_id,))

        selected_branch = row_to_dict(
            cursor,
            cursor.fetchone()
        )

    # --------------------------------------------------------
    # SELECTED SECTION
    # --------------------------------------------------------

    selected_section = None

    if section_id:

        cursor.execute("""
            SELECT id, name
            FROM sections
            WHERE id = ?
        """, (section_id,))

        selected_section = row_to_dict(
            cursor,
            cursor.fetchone()
        )

    connection.close()

    return render_template(
        "analytics.html",
        selected_semester=semester,

        total_results=total_results,
        avg_sgpa=avg_sgpa,
        class_average=class_average,
        pass_rate=pass_rate,

        passed_count=passed_count,
        failed_count=failed_count,

        top_performer=top_performer,

        student_performance=
            student_performance,

        subject_performance=
            subject_performance,

        highest_subject=
            highest_subject,

        lowest_subject=
            lowest_subject,

        semester_performance=
            semester_performance,

        branches=branches,
        sections=sections,

        selected_branch=
            selected_branch,

        selected_section=
            selected_section,

        selected_branch_id=
            branch_id,

        selected_section_id=
            section_id
    )


@app.route("/student/add", methods=["POST"])
def add_student():
    roll_no = request.form.get("roll_no", "").strip()
    name = request.form.get("name", "").strip()
    batch = request.form.get("batch", "").strip()
    course_id = request.form.get("course_id", type=int)
    branch_id = request.form.get("branch_id", type=int)
    semester = selected_semester()
    section_name = request.form.get("section", "").strip()
    if not roll_no or not name:
        abort(400, description="Student name and roll number are required.")
    with closing(get_connection()) as connection:
        branch = connection.execute(
            "SELECT id FROM branches WHERE id = ? AND course_id = ?",
            (branch_id, course_id)).fetchone()
        section = connection.execute("""
            SELECT id FROM sections WHERE branch_id = ? AND semester = ? AND name = ?
        """, (branch_id, semester, section_name)).fetchone()
        if not branch or not section:
            abort(400, description="Choose a valid course, branch, semester and configured section.")
        try:
            with connection:
                connection.execute("""
                    INSERT INTO students (roll_no, name, course_id, branch_id, section_id, batch)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (roll_no, name, course_id, branch_id, section[0], batch))
        except sqlite3.IntegrityError:
            abort(400, description="That roll number already exists. Please use a unique roll number.")
    flash("Student added successfully.", "success")
    return redirect(url_for("student_records"))


@app.route("/student/<int:student_id>/edit", methods=["POST"])
def edit_student(student_id):
    name = request.form.get("name", "").strip()
    roll_no = request.form.get("roll_no", "").strip()
    batch = request.form.get("batch", "").strip()
    with closing(get_connection()) as connection:
        student_record(connection, student_id)
        if not name or not roll_no:
            abort(400, description="Student name and roll number are required.")
        try:
            with connection:
                connection.execute("""
                    UPDATE students SET name = ?, roll_no = ?, batch = ? WHERE id = ?
                """, (name, roll_no, batch, student_id))
        except sqlite3.IntegrityError:
            abort(400, description="That roll number is already assigned to another student.")
    flash("Student details updated.", "success")
    return redirect(url_for("student_profile", student_id=student_id))


@app.route("/student/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id):
    with closing(get_connection()) as connection:
        student_record(connection, student_id)
        with connection:
            connection.execute("DELETE FROM results WHERE student_id = ?", (student_id,))
            connection.execute("DELETE FROM semester_results WHERE student_id = ?", (student_id,))
            connection.execute("DELETE FROM students WHERE id = ?", (student_id,))
    flash("Student and associated results deleted.", "success")
    return redirect(url_for("student_records"))


@app.route("/student/<int:student_id>")
def student_profile(student_id):
    semester = selected_semester()
    with closing(get_connection()) as connection:
        student = student_record(connection, student_id)
        semester_results = query(connection, """
            SELECT semester, sgpa, percentage, result FROM semester_results
            WHERE student_id = ? ORDER BY semester
        """, (student_id,))
        subject_results = result_subjects(connection, student_id, semester)
        subjects = query(connection, """
            SELECT id, code, name, credits FROM subjects
            WHERE branch_id = ? AND semester = ? ORDER BY id
        """, (student["branch_id"], semester))
    current_result = next((r for r in semester_results if r["semester"] == semester), None)
    if subject_results:
        actual = calculate_performance(subject_results)
        # Display the same prototype grade labels as the shared result engine.
        subject_results = actual["subjects"]
    else:
        actual = None
    risk = risk_level(actual)
    marks_by_id = {s["id"]: s["marks"] for s in subject_results}
    marks_by_name = {s["name"]: s["marks"] for s in subject_results}
    for subject in subjects:
        subject["marks"] = marks_by_id.get(subject["id"], marks_by_name.get(subject["name"], ""))
    return render_template(
        "student.html", student=student, semester_results=semester_results,
        subject_results=subject_results, subjects=subjects, current_result=current_result,
        actual=actual, risk=risk, selected_semester=semester,
        cgpa=sum(r["sgpa"] for r in semester_results) / len(semester_results) if semester_results else 0
    )


@app.route("/student/<int:student_id>/result/add", methods=["POST"])
def add_result(student_id):
    semester = selected_semester()
    with closing(get_connection()) as connection:
        student = student_record(connection, student_id)
        subjects = query(connection, """
            SELECT id, name, credits FROM subjects WHERE branch_id = ? AND semester = ? ORDER BY id
        """, (student["branch_id"], semester))
        if not subjects:
            abort(400, description=f"No Semester {semester} subjects are configured for this branch.")
        try:
            for index, subject in enumerate(subjects):
                subject["marks"] = parse_marks(request.form.get(f"marks_{index}"))
            performance = calculate_performance(subjects)
        except ValueError as error:
            abort(400, description=str(error))
        # Validate the full form first; replace details and summary in one transaction.
        with connection:
            connection.execute("DELETE FROM results WHERE student_id = ? AND semester = ?",
                               (student_id, semester))
            connection.execute("DELETE FROM semester_results WHERE student_id = ? AND semester = ?",
                               (student_id, semester))
            for subject in performance["subjects"]:
                connection.execute("""
                    INSERT INTO results (student_id, subject_id, semester, marks, grade, grade_point)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (student_id, subject["id"], semester, subject["marks"],
                      subject["grade"], subject["grade_point"]))
            connection.execute("""
                INSERT INTO semester_results (student_id, semester, sgpa, percentage, result)
                VALUES (?, ?, ?, ?, ?)
            """, (student_id, semester, performance["sgpa"],
                  performance["percentage"], performance["result"]))
    flash(f"Semester {semester} results saved.", "success")
    return redirect(url_for("student_profile", student_id=student_id, semester=semester))


@app.route("/student/<int:student_id>/twin", methods=["GET", "POST"])
def student_twin(student_id):
    semester = selected_semester()
    with closing(get_connection()) as connection:
        # Enforce the Twin boundary in SQLite as well as in application logic.
        connection.execute("PRAGMA query_only = ON")
        student = student_record(connection, student_id)
        subjects = result_subjects(connection, student_id, semester)
        history = query(connection, """
            SELECT semester, sgpa, percentage, result FROM semester_results
            WHERE student_id = ? ORDER BY semester
        """, (student_id,))
    actual = calculate_performance(subjects) if subjects else None
    simulated = actual
    solution, error = None, None
    target = request.form.get("target_sgpa", "8.50")
    status = 200
    if request.method == "POST" and actual:
        action = request.form.get("action", "simulate")
        try:
            if action not in ("simulate", "solve", "reset"):
                raise ValueError("Choose Run simulation, Calculate path, or Reset to actual.")
            if action != "reset":
                scenario = [
                    {**subject, "marks": parse_marks(request.form.get(f"marks_{subject['id']}"))}
                    for subject in subjects
                ]
                simulated = calculate_performance(scenario)
                if action == "solve":
                    solution = solve_target(scenario, target)
                    simulated = solution["performance"]
        except (ValueError, TypeError) as invalid:
            error = str(invalid)
            status = 400
    elif request.method == "POST" and not actual:
        error = "Add semester results to this student before running a simulation."
        status = 400
    chart_data = {
        "labels": [s["code"] or s["name"] for s in subjects],
        "actual": [s["marks"] for s in subjects],
        "simulated": [s["marks"] for s in simulated["subjects"]] if simulated else []
    }
    return render_template(
        "twin.html", student=student, selected_semester=semester, semester_results=history,
        actual=actual, simulated=simulated, solution=solution, target=target, error=error,
        actual_risk=risk_level(actual), simulated_risk=risk_level(simulated),
        insights=recommendations(actual, simulated) if actual else [],
        sgpa_difference=round(simulated["sgpa"] - actual["sgpa"], 2) if actual else 0,
        percentage_difference=round(simulated["percentage"] - actual["percentage"], 2) if actual else 0,
        chart_data=chart_data
    ), status


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
def user_error(error):
    return render_template("error.html", status=error.code, message=error.description), error.code


@app.errorhandler(500)
def server_error(error):
    return render_template(
        "error.html", status=500,
        message="We couldn't complete that request. Please return to the dashboard and try again."
    ), 500


if __name__ == "__main__":
    app.run(debug=False)