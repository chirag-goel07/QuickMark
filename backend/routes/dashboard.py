from flask import Blueprint, jsonify

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import emails
from services import sessions as svc
from services.attendance_stats import low_attendance_students, overall_percentage

bp = Blueprint("dashboard", __name__, url_prefix="/api/teacher")


@bp.get("/dashboard")
@login_required("teacher")
def dashboard():
    db = get_db()
    t = current_teacher()

    total_classes = db.execute("SELECT COUNT(*) FROM classes WHERE teacher_id = ?", (t["id"],)).fetchone()[0]
    total_students = db.execute(
        """SELECT COUNT(*) FROM students st
           JOIN sections sec ON sec.id = st.section_id
           JOIN classes c ON c.id = sec.class_id
           WHERE c.teacher_id = ?""", (t["id"],)).fetchone()[0]
    todays_sessions = db.execute(
        "SELECT COUNT(*) FROM attendance_sessions WHERE teacher_id = ? AND date(created_at) = date('now', 'localtime')",
        (t["id"],)).fetchone()[0]
    todays_groups = db.execute(
        """SELECT id, label, status, total_students FROM attendance_sessions
           WHERE teacher_id = ? AND session_type = 'group' AND date(created_at) = date('now', 'localtime')
           ORDER BY id DESC""", (t["id"],)).fetchall()

    class_list = []
    for c in db.execute("SELECT id, name FROM classes WHERE teacher_id = ? ORDER BY name", (t["id"],)).fetchall():
        secs = db.execute("SELECT id, name FROM sections WHERE class_id = ? ORDER BY name", (c["id"],)).fetchall()
        class_list.append({"id": c["id"], "name": c["name"],
                           "sections": [{"id": s["id"], "name": s["name"]} for s in secs]})

    threshold = t["warning_threshold"]
    low = low_attendance_students(db, t["id"], threshold)
    for s in low:
        s["subject"], s["body"] = emails.warning_message(t["name"], s["name"], s["percentage"], threshold)
    return jsonify(
        teacher={"name": t["name"]},
        stats={
            "total_classes": total_classes,
            "total_students": total_students,
            "todays_sessions": todays_sessions,
            "overall_attendance": overall_percentage(db, t["id"]),   # null until sessions have ended
        },
        threshold=threshold,
        classes=class_list,
        todays_groups=[dict(g) for g in todays_groups],
        low_attendance=low,
        requests=svc.pending_requests_for_teacher(db, t["id"], 20),
    )
