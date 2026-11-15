from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import reports
from services import sessions as svc
from services import realtime
from services.csvutil import csv_response
from services.xlsx import xlsx_response

bp = Blueprint("history", __name__, url_prefix="/api/teacher/history")


def _filters():
    a = request.args
    return dict(class_id=a.get("class_id", type=int), kind=a.get("type"), date_from=a.get("from"), date_to=a.get("to"))


@bp.get("")
@login_required("teacher")
def list_history():
    db, t = get_db(), current_teacher()
    return jsonify(sessions=reports.history_rows(db, t["id"], **_filters()))


@bp.get("/export.csv")
@login_required("teacher")
def history_csv():
    db, t = get_db(), current_teacher()
    rows = reports.history_rows(db, t["id"], **_filters())
    return csv_response("attendance_history.csv",
                        ["Date", "Class / Group", "Subject", "Type", "Total students", "Present", "Absent", "Attendance %"],
                        [[r["date"], r["label"], r["subject"] or "", r["type"], r["total"], r["present"], r["absent"],
                          "" if r["percentage"] is None else r["percentage"]] for r in rows])


def _own_ended(db, t, session_id):
    s = svc.get_session(db, session_id)
    if not s or s["teacher_id"] != t["id"] or s["status"] != "ended":
        return None
    return s


@bp.get("/<int:session_id>")
@login_required("teacher")
def session_detail(session_id):
    db, t = get_db(), current_teacher()
    s = _own_ended(db, t, session_id)
    if not s:
        return jsonify(error="Session not found."), 404
    st = svc.build_state(db, s, 0)
    st.update(started_at=s["started_at"], ended_at=s["ended_at"], date=(s["started_at"] or "")[:10],
              percentage=reports.pct(st["present"], st["total"]))
    return jsonify(st)


@bp.put("/<int:session_id>/records")
@login_required("teacher")
def edit_record(session_id):
    """Edit attendance after the session ended: set one student to present or absent (logged in attendance_edits)."""
    import time
    db, t = get_db(), current_teacher()
    s = _own_ended(db, t, session_id)
    if not s:
        return jsonify(error="Session not found."), 404
    data = request.get_json(silent=True) or {}
    try:
        svc.teacher_set_attendance(db, s, data.get("student_id"), data.get("status"), time.time(), t["id"], ("ended",))
    except svc.SessionError as e:
        return jsonify(error=e.message), e.status
    st = svc.build_state(db, svc.get_session(db, session_id), 0)
    st.update(percentage=reports.pct(st["present"], st["total"]), date=(s["started_at"] or "")[:10],
              started_at=s["started_at"], ended_at=s["ended_at"])
    return jsonify(st)


@bp.get("/<int:session_id>.csv")
@login_required("teacher")
def session_csv(session_id):
    db, t = get_db(), current_teacher()
    s = _own_ended(db, t, session_id)
    if not s:
        return jsonify(error="Session not found."), 404
    rows = db.execute(
        """SELECT st.roll_no, st.name, ar.status, ar.marked_at, ar.marked_via FROM attendance_records ar
           JOIN students st ON st.id = ar.student_id WHERE ar.session_id = ? ORDER BY st.roll_no""", (session_id,)).fetchall()
    via = {"qr": "QR scan", "teacher": "Teacher edit", "request": "Request approved"}
    return csv_response(f"session_{session_id}.csv", ["Roll No", "Name", "Status", "Marked at", "Marked by"],
                        [[r["roll_no"], r["name"], r["status"], r["marked_at"] if r["status"] == "present" else "",
                          via.get(r["marked_via"], r["marked_via"]) if r["status"] == "present" or r["marked_via"] != "qr" else ""] for r in rows])


@bp.get("/<int:session_id>.xlsx")
@login_required("teacher")
def session_xlsx(session_id):
    """One Excel sheet per section (matches the section-wise edit boxes)."""
    db, t = get_db(), current_teacher()
    s = _own_ended(db, t, session_id)
    if not s:
        return jsonify(error="Session not found."), 404
    via = {"qr": "QR scan", "teacher": "Teacher edit", "request": "Request approved"}
    sheets = [(b["label"], ["Roll No", "Name", "Status"], [[x["roll_no"], x["name"], x["status"].capitalize()] for x in b["students"]])
              for b in svc.section_boxes(db, session_id)]
    return xlsx_response(f"session_{session_id}.xlsx", sheets or [("Session", ["Roll No", "Name", "Status"], [])])
