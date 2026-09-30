"""Calculation and Flask regression checks using disposable SQLite backups."""

import hashlib
from copy import deepcopy
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import template_rendered

import database
from academic import calculate_performance, get_grade_point, recommendations, risk_level, solve_target


MARKS = [95, 85, 75, 65, 55, 35]
CREDITS = [3, 4, 2, 4, 4, 3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def backup_database(source, destination):
    """Read the original through a read-only SQLite connection."""
    with sqlite3.connect(Path(source).as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as copied:
            original.backup(copied)
    original.close()
    copied.close()


class PageParser(HTMLParser):
    """Inspect rendered form contracts and JSON chart payloads without a browser."""

    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.payloads = []
        self.current_form = None
        self.json_script = None
        self.nested_forms = False
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "form":
            self.nested_forms = self.nested_forms or self.current_form is not None
            self.current_form = {"attributes": attributes, "fields": []}
            self.forms.append(self.current_form)
        elif tag in ("input", "select", "button", "textarea") and self.current_form is not None:
            self.current_form["fields"].append(attributes)
        elif tag == "script" and attributes.get("type") == "application/json":
            self.json_script = ""

    def handle_data(self, data):
        if self.json_script is not None:
            self.json_script += data

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None
        elif tag == "script" and self.json_script is not None:
            self.payloads.append(json.loads(self.json_script))
            self.json_script = None


class AcademicRulesTests(unittest.TestCase):
    def subjects(self, marks=MARKS, credits=CREDITS):
        return [{"id": index + 1, "name": f"Subject {index + 1}", "code": f"S{index + 1}",
                 "marks": mark, "credits": credit}
                for index, (mark, credit) in enumerate(zip(marks, credits))]

    def test_every_grade_threshold(self):
        expected = {
            0: (0, "F"), 39: (0, "F"), 40: (5, "D"), 49: (5, "D"),
            50: (6, "C"), 59: (6, "C"), 60: (7, "B"), 69: (7, "B"),
            70: (8, "B+"), 79: (8, "B+"), 80: (9, "A"), 89: (9, "A"),
            90: (10, "A+"), 100: (10, "A+"),
        }
        for marks, grade in expected.items():
            with self.subTest(marks=marks):
                self.assertEqual(get_grade_point(marks), grade)

    def test_credit_weighted_regression_and_no_input_mutation(self):
        subjects = self.subjects()
        before = deepcopy(subjects)
        performance = calculate_performance(subjects)
        self.assertEqual(performance["sgpa"], 6.7)
        self.assertEqual(performance["percentage"], 68.33)
        self.assertEqual(performance["result"], "FAIL")
        self.assertEqual(performance["total_credits"], 20)
        self.assertEqual(subjects, before)

    def test_pass_requires_every_subject_to_reach_40(self):
        performance = calculate_performance(self.subjects([100, 100, 100, 100, 100, 39]))
        self.assertGreater(performance["sgpa"], 6.5)
        self.assertEqual(performance["result"], "FAIL")
        performance = calculate_performance(self.subjects([40] * 6))
        self.assertEqual(performance["result"], "PASS")
        self.assertEqual(performance["sgpa"], 5)

    def test_risk_boundaries_and_low_marks(self):
        cases = [(8, "FAIL", 39, "high"), (4.99, "PASS", 60, "high"),
                 (5, "PASS", 50, "moderate"), (6.49, "PASS", 60, "moderate"),
                 (8, "PASS", 44, "moderate"), (6.5, "PASS", 45, "stable")]
        for sgpa, result, marks, expected in cases:
            with self.subTest(sgpa=sgpa, marks=marks):
                self.assertEqual(risk_level({"sgpa": sgpa, "result": result,
                                            "subjects": [{"marks": marks}]})["level"], expected)

    def test_solver_prefers_credit_impact_at_a_nearby_threshold(self):
        subjects = self.subjects([69, 69], [4, 1])
        before = deepcopy(subjects)
        solution = solve_target(subjects, 7.8)
        self.assertEqual(solution["performance"]["sgpa"], 7.8)
        self.assertEqual([row["marks"] for row in solution["performance"]["subjects"]], [70, 69])
        self.assertEqual(solution["priorities"][0]["impact"], 0.8)
        self.assertEqual(subjects, before)
        self.assertEqual(solve_target(subjects, 7.8), solution)

    def test_solver_handles_multiple_upgrades_and_already_satisfied_targets(self):
        subjects = self.subjects()
        before = deepcopy(subjects)
        solution = solve_target(subjects, 8.5)
        self.assertGreaterEqual(solution["performance"]["sgpa"], 8.5)
        for original, suggested in zip(subjects, solution["performance"]["subjects"]):
            self.assertGreaterEqual(suggested["marks"], original["marks"])
            self.assertLessEqual(suggested["marks"], 100)
            if suggested["marks"] != original["marks"]:
                self.assertIn(suggested["marks"], (40, 50, 60, 70, 80, 90))
        self.assertEqual(subjects, before)
        already = solve_target(subjects, 6)
        self.assertEqual(already["performance"]["sgpa"], 6.7)
        self.assertEqual(already["priorities"], [])

    def test_solver_rejects_unavailable_targets(self):
        for target in (-1, 10.01, float("inf"), float("nan"), "abc"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    solve_target(self.subjects(), target)
        maximum = solve_target(self.subjects(), 10)
        self.assertEqual(maximum["performance"]["sgpa"], 10)

    def test_empty_engine_state_and_invalid_academic_values(self):
        empty = calculate_performance([])
        self.assertEqual((empty["sgpa"], empty["percentage"], empty["result"]), (0, 0, "NO RESULTS"))
        self.assertEqual(risk_level(empty)["level"], "unknown")
        self.assertEqual(solve_target([], 8.5)["status"], "no_data")
        for marks, credits in ((-1, 3), (101, 3), (float("nan"), 3), (70, 0), (70, -1)):
            with self.subTest(marks=marks, credits=credits):
                with self.assertRaises(ValueError):
                    calculate_performance(self.subjects([marks], [credits]))

    def test_recommendations_explain_the_simulated_change(self):
        subjects = self.subjects([69, 69], [4, 1])
        actual = calculate_performance(subjects)
        simulated = calculate_performance(self.subjects([70, 69], [4, 1]))
        before = deepcopy((actual, simulated))
        insights = recommendations(actual, simulated)
        self.assertTrue(insights)
        self.assertTrue(all(isinstance(insight, str) for insight in insights))
        self.assertIn("0.80", " ".join(insights))
        self.assertEqual((actual, simulated), before)


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live_database = Path(database.DB_NAME).resolve()
        cls.original_digest = digest(cls.live_database)
        cls.baseline_directory = tempfile.TemporaryDirectory(prefix="acadtwin-baseline-")
        cls.baseline = Path(cls.baseline_directory.name) / "baseline.db"
        backup_database(cls.live_database, cls.baseline)
        # Redirect the database before app import, including create_database().
        cls.database_patch = patch.object(database, "DB_NAME", str(cls.baseline))
        cls.database_patch.start()
        cls.module = importlib.import_module("app")
        cls.application = cls.module.app
        cls.application.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.database_patch.stop()
        cls.baseline_directory.cleanup()
        if digest(cls.live_database) != cls.original_digest:
            raise AssertionError("The live acadtwin.db changed during the test suite.")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="acadtwin-test-")
        self.db_path = Path(self.directory.name) / "test.db"
        backup_database(self.baseline, self.db_path)
        database.DB_NAME = str(self.db_path)
        self.client = self.application.test_client()
        self.context = {}

        def captured(sender, template, context, **extra):
            self.context = dict(context)

        self.receiver = captured
        template_rendered.connect(self.receiver, self.application)
        with self.connect() as connection:
            self.course_id = connection.execute(
                "INSERT INTO courses (name) VALUES ('Test Course')"
            ).lastrowid
            self.branch_id = connection.execute(
                "INSERT INTO branches (course_id, name) VALUES (?, 'Test Computing')",
                (self.course_id,),
            ).lastrowid
            self.other_branch_id = connection.execute(
                "INSERT INTO branches (course_id, name) VALUES (?, 'Test Electronics')",
                (self.course_id,),
            ).lastrowid
            self.section_a = connection.execute(
                "INSERT INTO sections (branch_id, semester, name) VALUES (?, 3, 'A')",
                (self.branch_id,),
            ).lastrowid
            self.section_b = connection.execute(
                "INSERT INTO sections (branch_id, semester, name) VALUES (?, 3, 'B')",
                (self.branch_id,),
            ).lastrowid
            connection.execute(
                "INSERT INTO sections (branch_id, semester, name) VALUES (?, 3, 'A')",
                (self.other_branch_id,),
            )
            for branch_id in (self.branch_id, self.other_branch_id):
                for index, credits in enumerate(CREDITS):
                    connection.execute(
                        """INSERT INTO subjects (code, name, branch_id, semester, credits)
                           VALUES (?, ?, ?, 3, ?)""",
                        (f"QA-{branch_id}-{index}", f"Test Subject {index + 1}", branch_id, credits),
                    )
        connection.close()

    def tearDown(self):
        template_rendered.disconnect(self.receiver, self.application)
        database.DB_NAME = str(self.baseline)
        self.directory.cleanup()
        self.assertEqual(digest(self.live_database), self.original_digest)

    def connect(self):
        return sqlite3.connect(self.db_path)

    def query(self, sql, parameters=()):
        connection = self.connect()
        try:
            return connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()

    def snapshot(self):
        connection = self.connect()
        try:
            return tuple(connection.iterdump())
        finally:
            connection.close()

    def add_student(self, roll="TEST-001", section="A", branch_id=None):
        response = self.client.post("/student/add", data={
            "roll_no": roll, "name": "Test Student", "course_id": self.course_id,
            "branch_id": branch_id or self.branch_id, "semester": 3,
            "section": section, "batch": "2025-2029",
        })
        self.assertEqual(response.status_code, 302)
        rows = self.query("SELECT id FROM students WHERE roll_no = ?", (roll,))
        self.assertEqual(len(rows), 1)
        return rows[0][0]

    def save_result(self, student_id, marks=MARKS):
        return self.client.post(f"/student/{student_id}/result/add", data={
            "semester": 3, **{f"marks_{index}": mark for index, mark in enumerate(marks)}
        })

    def twin_payload(self, student_id, marks, action="simulate", target="8.50"):
        subjects = self.query(
            "SELECT subject_id FROM results WHERE student_id = ? AND semester = 3 ORDER BY subject_id",
            (student_id,),
        )
        return {"semester": 3, "action": action, "target_sgpa": target,
                **{f"marks_{row[0]}": mark for row, mark in zip(subjects, marks)}}

    def test_main_pages_and_static_assets_load(self):
        for path in ("/", "/students", "/digital-twin", "/analytics",
                     "/static/css/style.css", "/static/js/app.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                if not path.startswith("/static/"):
                    self.assertIn(b"AcadTwin", response.data)
                    self.assertNotIn(b"Traceback", response.data)
                response.close()

    def test_add_edit_and_duplicate_student_validation(self):
        student_id = self.add_student()
        response = self.client.post(f"/student/{student_id}/edit", data={
            "name": "Updated Student", "roll_no": "TEST-EDITED", "batch": "2026-2030"
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.query(
            "SELECT name, roll_no, batch FROM students WHERE id = ?", (student_id,)
        ), [("Updated Student", "TEST-EDITED", "2026-2030")])
        before = self.query("SELECT COUNT(*) FROM students")
        response = self.client.post("/student/add", data={
            "name": "Duplicate", "roll_no": "TEST-EDITED", "course_id": self.course_id,
            "branch_id": self.branch_id, "semester": 3, "section": "A",
        })
        self.assertIn(response.status_code, (302, 400))
        self.assertEqual(self.query("SELECT COUNT(*) FROM students"), before)
        self.assertEqual(self.client.get(f"/student/{student_id}").status_code, 200)

    def test_result_regression_and_replacement(self):
        student_id = self.add_student()
        self.assertEqual(self.save_result(student_id).status_code, 302)
        self.assertEqual(self.query(
            "SELECT percentage, sgpa, result FROM semester_results WHERE student_id = ?",
            (student_id,),
        ), [(68.33, 6.7, "FAIL")])
        self.assertEqual(self.query(
            "SELECT grade_point FROM results WHERE student_id = ? ORDER BY subject_id",
            (student_id,),
        ), [(10.0,), (9.0,), (8.0,), (7.0,), (6.0,), (0.0,)])
        self.assertEqual(self.save_result(student_id, [90] * 6).status_code, 302)
        self.assertEqual(self.query(
            "SELECT percentage, sgpa, result FROM semester_results WHERE student_id = ?",
            (student_id,),
        ), [(90.0, 10.0, "PASS")])
        self.assertEqual(self.query("SELECT COUNT(*) FROM results WHERE student_id = ?", (student_id,)), [(6,)])

    def test_invalid_result_marks_preserve_previous_result(self):
        student_id = self.add_student()
        self.save_result(student_id)
        before = self.snapshot()
        for invalid in ("-1", "101", "abc", "", "69.5", "nan"):
            with self.subTest(invalid=invalid):
                marks = list(MARKS)
                marks[4] = invalid
                response = self.save_result(student_id, marks)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)
        response = self.client.post(f"/student/{student_id}/result/add", data={"semester": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_delete_removes_only_selected_student_and_related_rows(self):
        student_id = self.add_student()
        other_id = self.add_student("TEST-002")
        self.save_result(student_id)
        self.save_result(other_id)
        other_before = self.query("SELECT * FROM results WHERE student_id = ?", (other_id,))
        self.assertEqual(self.client.get(f"/student/{student_id}/delete").status_code, 405)
        self.assertEqual(self.client.post(f"/student/{student_id}/delete").status_code, 302)
        for table in ("students", "results", "semester_results"):
            field = "id" if table == "students" else "student_id"
            self.assertEqual(self.query(f"SELECT COUNT(*) FROM {table} WHERE {field} = ?", (student_id,)), [(0,)])
        self.assertEqual(self.query("SELECT * FROM results WHERE student_id = ?", (other_id,)), other_before)

    def test_branch_specific_subjects_are_used_for_results(self):
        student_id = self.add_student(branch_id=self.other_branch_id)
        self.assertEqual(self.save_result(student_id).status_code, 302)
        self.assertEqual(self.query(
            """SELECT DISTINCT sub.branch_id FROM results r
               JOIN subjects sub ON sub.id = r.subject_id WHERE r.student_id = ?""",
            (student_id,),
        ), [(self.other_branch_id,)])

    def test_dashboard_and_analytics_filters_use_matching_records(self):
        first = self.add_student()
        second = self.add_student("TEST-002", section="B")
        third = self.add_student("TEST-003", branch_id=self.other_branch_id)
        self.save_result(first)
        self.save_result(second, [90] * 6)
        self.save_result(third, [40] * 6)
        for page in ("/", "/analytics"):
            response = self.client.get(page, query_string={"branch_id": self.branch_id})
            self.assertEqual(response.status_code, 200)
            self.assertAlmostEqual(self.context["avg_sgpa"], 8.35)
            self.assertAlmostEqual(self.context["pass_rate"], 50)
            self.assertEqual(self.context["passed_count"], 1)
            self.assertEqual(self.context["failed_count"], 1)
            response = self.client.get(page, query_string={
                "branch_id": self.branch_id, "section_id": self.section_b,
            })
            self.assertEqual(response.status_code, 200)
            self.assertAlmostEqual(self.context["avg_sgpa"], 10)
            self.assertAlmostEqual(self.context["pass_rate"], 100)
            self.assertEqual(self.context["passed_count"], 1)
            self.assertEqual(self.context["failed_count"], 0)
        self.client.get("/", query_string={"course_id": self.course_id})
        self.assertEqual(self.context["total_students"], 3)
        self.assertAlmostEqual(self.context["avg_sgpa"], (6.7 + 10 + 5) / 3)

    def test_twin_simulation_changes_calculation_without_any_database_write(self):
        student_id = self.add_student()
        self.save_result(student_id)
        before = self.snapshot()
        before_digest = digest(self.db_path)
        self.assertEqual(self.client.get(f"/student/{student_id}/twin").status_code, 200)
        response = self.client.post(f"/student/{student_id}/twin", data=self.twin_payload(student_id, [90] * 6))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Simulation only", response.data)
        self.assertIn(b"10.00", response.data)
        self.assertIn(b"6.70", response.data)
        self.assertEqual(self.context["actual"]["sgpa"], 6.7)
        self.assertEqual(self.context["actual"]["result"], "FAIL")
        self.assertEqual(self.context["simulated"]["sgpa"], 10)
        self.assertEqual(self.context["simulated"]["result"], "PASS")
        self.assertEqual(self.context["sgpa_difference"], 3.3)
        self.assertEqual(self.context["chart_data"]["actual"], MARKS)
        self.assertEqual(self.context["chart_data"]["simulated"], [90] * 6)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(digest(self.db_path), before_digest)
        self.assertEqual(self.client.get(f"/student/{student_id}").status_code, 200)
        self.assertEqual(self.query(
            "SELECT marks FROM results WHERE student_id = ? ORDER BY subject_id", (student_id,)
        ), [(mark,) for mark in MARKS])

    def test_twin_solver_and_invalid_inputs_leave_database_unchanged(self):
        student_id = self.add_student()
        self.save_result(student_id)
        before = self.snapshot()
        before_digest = digest(self.db_path)
        response = self.client.post(f"/student/{student_id}/twin", data=self.twin_payload(student_id, MARKS, "solve"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"8.50", response.data)
        self.assertGreaterEqual(self.context["simulated"]["sgpa"], 8.5)
        for target in ("10.01", "-1", "nan", "inf", "abc"):
            with self.subTest(target=target):
                response = self.client.post(f"/student/{student_id}/twin", data=self.twin_payload(student_id, MARKS, "solve", target))
                self.assertEqual(response.status_code, 400)
        for invalid in ("101", "-1", "abc", "40.5"):
            marks = list(MARKS)
            marks[0] = invalid
            response = self.client.post(f"/student/{student_id}/twin", data=self.twin_payload(student_id, marks))
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(digest(self.db_path), before_digest)

    def test_twin_reset_restores_actual_and_missing_marks_are_rejected(self):
        student_id = self.add_student()
        self.save_result(student_id)
        before = self.snapshot()
        response = self.client.post(f"/student/{student_id}/twin", data={"action": "reset", "semester": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.context["actual"], self.context["simulated"])
        self.assertEqual(self.context["sgpa_difference"], 0)
        response = self.client.post(f"/student/{student_id}/twin", data={"action": "simulate", "semester": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_dashboard_chart_values_and_search_follow_the_database(self):
        student_id = self.add_student()
        self.save_result(student_id)
        response = self.client.get("/", query_string={"branch_id": self.branch_id})
        self.assertEqual(response.status_code, 200)
        charts = self.context["chart_data"]
        self.assertEqual(charts["branch"], {"labels": ["Test Computing"], "values": [6.7]})
        self.assertEqual(charts["result"]["values"], [0, 1])
        self.assertEqual(charts["sgpa"]["values"], [0, 0, 1, 0, 0, 0])
        page = PageParser(response.get_data(as_text=True))
        self.assertIn(charts, page.payloads, "The rendered page must supply its real data to Chart.js.")
        self.assertEqual(self.context["at_risk_count"], 1)
        self.assertEqual(self.context["top_performer"]["id"], student_id)
        self.assertEqual(self.context["strongest_branch"]["branch_name"], "Test Computing")
        response = self.client.get("/students", query_string={"q": "TEST-001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([student["id"] for student in self.context["students"]], [student_id])
        self.client.get("/", query_string={"q": "THIS-STUDENT-DOES-NOT-EXIST"})
        self.assertEqual(self.context["total_students"], 0)
        self.assertEqual(self.context["chart_data"]["result"]["values"], [0, 0])

    def test_rendered_forms_have_working_field_names_and_twin_chart_json(self):
        student_id = self.add_student()
        self.save_result(student_id)
        profile = PageParser(self.client.get(f"/student/{student_id}").get_data(as_text=True))
        result_form = next(form for form in profile.forms
                           if form["attributes"].get("action") == f"/student/{student_id}/result/add")
        names = {field.get("name") for field in result_form["fields"]}
        self.assertTrue({"semester", *(f"marks_{index}" for index in range(6))} <= names)
        self.assertEqual(result_form["attributes"]["method"].lower(), "post")
        self.assertFalse(profile.nested_forms)

        response = self.client.get(f"/student/{student_id}/twin")
        twin = PageParser(response.get_data(as_text=True))
        twin_form = next(form for form in twin.forms
                         if form["attributes"].get("action") == f"/student/{student_id}/twin")
        names = {field.get("name") for field in twin_form["fields"]}
        required = set(self.twin_payload(student_id, MARKS))
        self.assertTrue(required <= names)
        actions = {field.get("value") for field in twin_form["fields"] if field.get("name") == "action"}
        self.assertEqual(actions, {"simulate", "solve", "reset"})
        self.assertFalse(twin.nested_forms)
        for field in twin_form["fields"]:
            if field.get("name", "").startswith("marks_"):
                self.assertEqual((field["min"], field["max"], field["step"]), ("0", "100", "1"))
                self.assertIn("required", field)
        self.assertIn(self.context["chart_data"], twin.payloads)
        self.assertEqual(self.context["chart_data"]["actual"], MARKS)

    def test_semester_results_and_filters_do_not_mix_semesters(self):
        student_id = self.add_student()
        self.save_result(student_id)
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO subjects (code, name, branch_id, semester, credits)
                   VALUES ('QA-SEM4', 'Semester Four Subject', ?, 4, 5)""", (self.branch_id,)
            )
        connection.close()
        response = self.client.post(f"/student/{student_id}/result/add", data={"semester": 4, "marks_0": 90})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.query(
            "SELECT semester, sgpa FROM semester_results WHERE student_id = ? ORDER BY semester", (student_id,)
        ), [(3, 6.7), (4, 10.0)])
        for page in ("/", "/analytics"):
            response = self.client.get(page, query_string={"branch_id": self.branch_id, "semester": 4})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.context["avg_sgpa"], 10)
            self.assertEqual(self.context["total_results"], 1)
        response = self.client.get(f"/student/{student_id}/twin", query_string={"semester": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.context["chart_data"]["actual"], [90])
        for invalid in ("0", "9", "abc"):
            self.assertEqual(self.client.get("/", query_string={"semester": invalid}).status_code, 400)

    def test_analytics_subject_performance_rankings_and_empty_filter(self):
        first = self.add_student()
        second = self.add_student("TEST-002", section="B")
        self.save_result(first)
        self.save_result(second, [90] * 6)
        response = self.client.get("/analytics", query_string={"branch_id": self.branch_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.context["top_performer"]["id"], second)
        self.assertEqual([row["id"] for row in self.context["student_performance"]], [second, first])
        self.assertEqual(len(self.context["subject_performance"]), 6)
        response = self.client.get("/analytics", query_string={"branch_id": 99999999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.context["total_results"], 0)
        self.assertEqual(self.context["subject_performance"], [])

    def test_no_results_and_missing_record_states(self):
        student_id = self.add_student()
        for path in (f"/student/{student_id}", f"/student/{student_id}/twin"):
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ("/student/99999999", "/student/99999999/twin"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b"Traceback", response.data)
        self.assertEqual(self.client.post("/student/99999999/result/add").status_code, 404)

    def test_empty_database_and_unconfigured_subjects_are_graceful(self):
        student_id = self.add_student()
        with self.connect() as connection:
            connection.execute("DELETE FROM subjects WHERE branch_id = ?", (self.branch_id,))
        connection.close()
        self.assertEqual(self.save_result(student_id).status_code, 400)
        with self.connect() as connection:
            for table in ("results", "semester_results", "students", "subjects", "sections", "branches", "courses"):
                connection.execute(f"DELETE FROM {table}")
        connection.close()
        for path in ("/", "/students", "/digital-twin", "/analytics"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b"Traceback", response.data)

    def test_existing_demo_records_remain_usable_and_unchanged(self):
        demos = self.query("SELECT id FROM students WHERE roll_no LIKE 'DEMO-%' ORDER BY id")
        self.assertTrue(demos, "The supplied database should contain presentation demo students.")
        before = self.snapshot()
        for (student_id,) in demos:
            with self.subTest(student_id=student_id):
                self.assertEqual(self.client.get(f"/student/{student_id}").status_code, 200)
                self.assertEqual(self.client.get(f"/student/{student_id}/twin").status_code, 200)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
