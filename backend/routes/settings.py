from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import alerts, emails
from services.ownership import clean_name

bp = Blueprint("settings", __name__, url_prefix="/api/teacher/settings")


def _payload(db, t):
    email = db.execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()["email"]
    return {"name": t["name"], "email": email, "phone": t["phone"] or "",
            "warning_threshold": t["warning_threshold"], "session_minutes": t["session_minutes"],
            "require_face": bool(t["require_face"]), "auto_alerts": bool(t["auto_alerts"]), "weekly_summary": bool(t["weekly_summary"]),
            "smtp_configured": emails.smtp_configured()}


def _int_in(value, lo, hi):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


@bp.get("")
@login_required("teacher")
def get_settings():
    db = get_db()
    return jsonify(_payload(db, current_teacher()))


@bp.put("")
@login_required("teacher")
def save_settings():
    db, t = get_db(), current_teacher()
    data = request.get_json(silent=True) or {}
    name, err = clean_name(data.get("name"), "Name", 80)
    if err:
        return jsonify(error=err), 400
    phone = data.get("phone") if isinstance(data.get("phone"), str) else ""
    phone = phone.strip()
    if len(phone) > 20:
        return jsonify(error="Phone number is too long."), 400
    threshold = _int_in(data.get("warning_threshold"), 1, 100)
    if threshold is None:
        return jsonify(error="Warning threshold must be a whole number from 1 to 100."), 400
    minutes = _int_in(data.get("session_minutes"), 1, 180)
    if minutes is None:
        return jsonify(error="Session duration must be a whole number of minutes from 1 to 180."), 400
    require_face = t["require_face"] if "require_face" not in data else (1 if data.get("require_face") in (True, 1, "1", "true") else 0)
    flag = lambda key, old: old if key not in data else (1 if data.get(key) in (True, 1, "1", "true") else 0)
    db.execute("UPDATE teachers SET name = ?, phone = ?, warning_threshold = ?, session_minutes = ?, require_face = ?, auto_alerts = ?, weekly_summary = ? WHERE id = ?",
               (name, phone or None, threshold, minutes, require_face, flag("auto_alerts", t["auto_alerts"]), flag("weekly_summary", t["weekly_summary"]), t["id"]))
    db.commit()
    return jsonify(_payload(db, current_teacher()))


@bp.post("/password")
@login_required("teacher")
def change_password():
    db = get_db()
    data = request.get_json(silent=True) or {}
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not check_password_hash(user["password_hash"], data.get("current_password") or ""):
        return jsonify(error="Your current password is wrong."), 400
    new = data.get("new_password")
    if not isinstance(new, str) or len(new) < 6:
        return jsonify(error="The new password must be at least 6 characters."), 400
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), user["id"]))
    db.commit()
    return jsonify(ok=True)


@bp.post("/send-summary")
@login_required("teacher")
def send_summary_now():
    """'Email me the summary now' (needs email to be set up on the server)."""
    if not alerts.send_summary(get_db(), current_teacher()["id"]):
        return jsonify(error="Email is not set up on this server (see the README, section on email)."), 503
    return jsonify(ok=True)
