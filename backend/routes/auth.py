import hmac
import hashlib
import secrets
import time

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db
import config
from middleware.auth import current_teacher
from services import emails, ratelimit

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role")
    if role not in ("teacher", "student") or not email or not password:
        return jsonify(error="Email, password and role are required."), 400

    user = get_db().execute(
        "SELECT * FROM users WHERE email = ? AND role = ?", (email, role)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Invalid email or password."), 401

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(ok=True, role=user["role"])


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    if "user_id" not in session:
        return jsonify(error="Not logged in."), 401
    if session["role"] == "teacher":
        t = current_teacher()
        return jsonify(role="teacher", name=t["name"])
    rows = get_db().execute(
        """SELECT st.name, st.roll_no, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v,
                  (t.require_face = 1 AND st.face_descriptor IS NULL) AS needs_face_setup, u.must_change_password
           FROM students st JOIN users u ON u.id = st.user_id JOIN sections sec ON sec.id = st.section_id
           JOIN classes c ON c.id = sec.class_id JOIN teachers t ON t.id = c.teacher_id
           WHERE st.user_id = ? ORDER BY c.name, sec.name, st.id""", (session["user_id"],)).fetchall()
    s = rows[0] if rows else None
    return jsonify(role="student", name=s["name"] if s else "", roll_no=s["roll_no"] if s else "", has_avatar=bool(s and s["has_avatar"]),
                   avatar_v=s["avatar_v"] if s else None, needs_face_setup=any(r["needs_face_setup"] for r in rows),
                   must_change_password=bool(s and s["must_change_password"]))


# ---------------------------------------------------------------- forgot password (6-digit code by email)
RESET_MINUTES = 15
RESET_MAX_TRIES = 5


def _code_hash(user_id, code):
    """Keyed hash: even someone who can read the database cannot turn it back into a code without the server's secret key."""
    return hmac.new(config.SECRET_KEY.encode(), f"reset:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _ip():
    return request.remote_addr or "?"


@bp.get("/forgot-status")
def forgot_status():
    return jsonify(email_enabled=emails.smtp_configured())


@bp.post("/forgot")
def forgot():
    """Always answers the same way, so nobody can use this to find out which emails are registered."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    role = data.get("role")
    if role not in ("teacher", "student") or not email or len(email) > 120:
        return jsonify(error="Enter your email address."), 400
    if not emails.smtp_configured():
        return jsonify(error="Password reset emails are not set up on this server. Please ask your teacher (students) or the administrator to reset your password."), 503
    if not ratelimit.allow("forgot-ip:" + _ip(), 10, 3600) or not ratelimit.allow("forgot-mail:" + email, 3, 3600):
        return jsonify(error="Too many requests. Please try again in an hour."), 429
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ? AND role = ?", (email, role)).fetchone()
    if user:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        db.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))
        db.execute("INSERT INTO password_resets (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
                   (user["id"], _code_hash(user["id"], code), time.time() + RESET_MINUTES * 60))
        db.commit()
        subject, body = emails.reset_code_message(email, code)
        emails.send_in_background(email, subject, body)
    return jsonify(ok=True, message="If that email is registered, a 6-digit code has been sent. It works for 15 minutes.")


@bp.post("/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    role, code, new = data.get("role"), str(data.get("code") or "").strip(), data.get("new_password")
    bad = jsonify(error="That code is wrong or has expired. Ask for a new one."), 400
    if role not in ("teacher", "student") or not email:
        return jsonify(error="Enter your email address."), 400
    if not isinstance(new, str) or len(new) < 6:
        return jsonify(error="The new password must be at least 6 characters."), 400
    if not ratelimit.allow("reset-ip:" + _ip(), 30, 3600) or not ratelimit.allow("reset-mail:" + email, 10, 3600):
        return jsonify(error="Too many attempts. Please try again in an hour."), 429
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ? AND role = ?", (email, role)).fetchone()
    row = db.execute("SELECT * FROM password_resets WHERE user_id = ?", (user["id"],)).fetchone() if user else None
    if not row or row["expires_at"] < time.time() or row["attempts"] >= RESET_MAX_TRIES:
        return bad
    if not hmac.compare_digest(row["code_hash"], _code_hash(user["id"], code)):
        db.execute("UPDATE password_resets SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        db.commit()
        return bad
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (generate_password_hash(new), user["id"]))
    db.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))          # a code works only once
    db.commit()
    return jsonify(ok=True)
