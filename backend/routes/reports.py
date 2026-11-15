from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import core, reports
from services.attendance_stats import overall_percentage
from services.csvutil import csv_response
from services.xlsx import xlsx_response

bp = Blueprint("reports", __name__, url_prefix="/api/teacher/reports")


@bp.get("")
@login_required("teacher")
def all_reports():
    db, t = get_db(), current_teacher()
    students = reports.student_rows(db, t["id"])
    threshold = t["warning_threshold"]
    for s in students:
        s["is_low"] = s["percentage"] is not None and s["percentage"] < threshold
    sessions = db.execute("SELECT COUNT(*) FROM attendance_sessions WHERE teacher_id = ? AND status = 'ended'", (t["id"],)).fetchone()[0]
    classes = reports.class_rows(db, t["id"])
    return jsonify(
        threshold=threshold,
        overall={"percentage": overall_percentage(db, t["id"]), "sessions": sessions,
                 "classes": len(classes), "students": len(students), "low": sum(1 for s in students if s["is_low"])},
        classes=classes, sections=reports.section_rows(db, t["id"]), students=students,
        low_students=core.sorted_by_value([s for s in students if s["is_low"]], key=lambda s: s["percentage"]),
        trend=reports.trend_rows(db, t["id"]))


@bp.get("/export.csv")
@login_required("teacher")
def reports_csv():
    db, t = get_db(), current_teacher()
    kind = request.args.get("kind", "students")
    p = lambda x: "" if x is None else x
    if kind == "classes":
        rows = reports.class_rows(db, t["id"])
        return csv_response("report_classes.csv", ["Class", "Students", "Present marks", "Total marks", "Attendance %"],
                            [[r["name"], r["students"], r["present"], r["total"], p(r["percentage"])] for r in rows])
    if kind == "sections":
        rows = reports.section_rows(db, t["id"])
        return csv_response("report_sections.csv", ["Class", "Section", "Students", "Present marks", "Total marks", "Attendance %"],
                            [[r["class_name"], r["section_name"], r["students"], r["present"], r["total"], p(r["percentage"])] for r in rows])
    if kind in ("students", "low"):
        rows = reports.student_rows(db, t["id"])
        if kind == "low":
            rows = [r for r in rows if r["percentage"] is not None and r["percentage"] < t["warning_threshold"]]
        return csv_response("report_low_attendance.csv" if kind == "low" else "report_students.csv",
                            ["Roll No", "Name", "Class", "Section", "Present", "Total sessions", "Attendance %"],
                            [[r["roll_no"], r["name"], r["class_name"], r["section_name"], r["present"], r["total"], p(r["percentage"])] for r in rows])
    return jsonify(error="Unknown report."), 400


@bp.get("/export.xlsx")
@login_required("teacher")
def reports_xlsx():
    """One workbook: Summary, Low attendance, then ONE SHEET PER SECTION (with a % column for every subject)."""
    db, t = get_db(), current_teacher()
    thr = t["warning_threshold"]
    p = lambda x: None if x is None else x
    students = reports.student_rows(db, t["id"])
    matrix = reports.subject_matrix(db, t["id"])
    sheets = [
        ("Summary", ["Class", "Section", "Students", "Present marks", "Total marks", "Attendance %"],
         [[r["class_name"], r["section_name"], r["students"], r["present"], r["total"], p(r["percentage"])] for r in reports.section_rows(db, t["id"])]),
        (f"Below {thr}%", ["Roll No", "Name", "Email", "Class", "Section", "Present", "Total sessions", "Attendance %"],
         [[r["roll_no"], r["name"], r["email"], r["class_name"], r["section_name"], r["present"], r["total"], r["percentage"]]
          for r in core.sorted_by_value([x for x in students if x["percentage"] is not None and x["percentage"] < thr], key=lambda x: x["percentage"])]),
    ]
    groups = {}
    for r in students:
        groups.setdefault((r["class_name"], r["section_name"]), []).append(r)
    for (cn, sn), rows in sorted(groups.items()):
        subjects = sorted({sub for r in rows for sub in matrix.get(r["id"], {})})
        head = ["Roll No", "Name", "Email", "Present", "Total sessions", "Attendance %", "Status"] + [f"{s} %" for s in subjects]
        body = []
        for r in core.natural_sorted(rows, key=lambda x: x["roll_no"]):
            low = r["percentage"] is not None and r["percentage"] < thr
            subs = []
            for s in subjects:
                pr, tot = matrix.get(r["id"], {}).get(s, (0, 0))
                subs.append(reports.pct(pr, tot) if tot else None)
            body.append([r["roll_no"], r["name"], r["email"], r["present"], r["total"], p(r["percentage"]),
                         "No sessions yet" if r["percentage"] is None else ("LOW" if low else "OK")] + subs)
        sheets.append((f"{cn} {sn}", head, body))
    return xlsx_response("attendance_report.xlsx", sheets, highlight_low=("Attendance %", thr))
