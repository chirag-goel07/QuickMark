from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import emails
from services.attendance_stats import low_attendance_students

bp = Blueprint("emails", __name__, url_prefix="/api/teacher/emails")
MAX_BATCH = 200


def _low(db, t):
    return low_attendance_students(db, t["id"], t["warning_threshold"])


def _wanted(low, raw_ids):
    """Only students that are CURRENTLY below the threshold and belong to this teacher can be emailed."""
    if raw_ids is None:
        return low
    try:
        ids = {int(x) for x in raw_ids}
    except (TypeError, ValueError):
        return None
    return [s for s in low if s["student_id"] in ids]


@bp.get("/status")
@login_required("teacher")
def status():
    return jsonify(smtp_configured=emails.smtp_configured())


@bp.get("/bulk-draft")
@login_required("teacher")
def bulk_draft():
    """Recipients + generic text for ONE draft (recipients go in BCC so students don't see each other)."""
    db, t = get_db(), current_teacher()
    subject, body = emails.bulk_message(t["name"], t["warning_threshold"])
    return jsonify(recipients=[s["email"] for s in _low(db, t)], subject=subject, body=body)


@bp.post("/opened")
@login_required("teacher")
def opened():
    """Records that the teacher opened a draft. It does NOT mean an email was sent."""
    db, t = get_db(), current_teacher()
    chosen = _wanted(_low(db, t), (request.get_json(silent=True) or {}).get("student_ids", []))
    if chosen is None:
        return jsonify(error="Invalid student list."), 400
    for s in chosen:
        subject, _ = emails.warning_message(t["name"], s["name"], s["percentage"], t["warning_threshold"])
        db.execute("INSERT INTO email_notifications (teacher_id, student_id, kind, subject) VALUES (?, ?, 'mailto_opened', ?)",
                   (t["id"], s["student_id"], subject))
    db.commit()
    return jsonify(ok=True, logged=len(chosen))


@bp.post("/send")
@login_required("teacher")
def send():
    """Actually sends one personal email per student through the server's SMTP account."""
    db, t = get_db(), current_teacher()
    if not emails.smtp_configured():
        return jsonify(error="Sending emails is not set up on the server. Use the Email Warning button to open a draft instead."), 503
    raw = (request.get_json(silent=True) or {}).get("student_ids")
    chosen = _wanted(_low(db, t), raw)
    if chosen is None:
        return jsonify(error="Invalid student list."), 400
    if not chosen:
        return jsonify(error="No students below the threshold to email."), 400
    if len(chosen) > MAX_BATCH:
        return jsonify(error=f"Too many recipients at once (max {MAX_BATCH})."), 400
    sent, failed = [], []
    for s in chosen:
        subject, body = emails.warning_message(t["name"], s["name"], s["percentage"], t["warning_threshold"])
        try:
            emails.send_one(s["email"], subject, body)
        except Exception as e:                      # keep going; report this student as failed
            failed.append({"name": s["name"], "error": str(e)[:120]})
            continue
        db.execute("INSERT INTO email_notifications (teacher_id, student_id, kind, subject) VALUES (?, ?, 'sent', ?)",
                   (t["id"], s["student_id"], subject))
        sent.append(s["name"])
    db.commit()
    return jsonify(sent=sent, failed=failed)
