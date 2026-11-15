"""Joining a section with its class code.

Teacher: switch a section's code Off / Open (students join at once) / Approval (teacher accepts each one), see + answer requests.
Student: preview a code, sign up as a new student, or (when logged in) join one more class.
"""
import re
import sqlite3

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import people, ratelimit
from services.ownership import clean_name, own_section

teacher_bp = Blueprint("join_teacher", __name__, url_prefix="/api/teacher/join")
public_bp = Blueprint("join_public", __name__, url_prefix="/api/join")
student_bp = Blueprint("join_student", __name__, url_prefix="/api/student")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MODES = ("off", "open", "approval")


def _fail(msg, code=400):
    return jsonify(error=msg), code


def _where(sec):
    return f"{sec['class_name']} - {sec['section_name']}"


def _guard_codes():
    """Stops someone from trying thousands of codes."""
    return ratelimit.allow("joincode:" + (request.remote_addr or "?"), 30, 600)


def _look_up(db, raw):
    if not _guard_codes():
        return None, _fail("Too many tries. Please wait a few minutes.", 429)
    sec = people.section_by_code(db, raw)
    if not sec:
        return None, _fail("That join code is not valid, or joining is switched off for it.", 404)
    return sec, None


# ================================================================ teacher
def _section_payload(sec):
    return {"section_id": sec["id"], "join_mode": sec["join_mode"], "join_code": people.format_code(sec["join_code"])}


@teacher_bp.put("/sections/<int:section_id>")
@login_required("teacher")
def set_join(section_id):
    """Body: {mode: off|open|approval, regenerate: bool}."""
    db, t = get_db(), current_teacher()
    sec = own_section(db, t["id"], section_id)
    if not sec:
        return _fail("Section not found.", 404)
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", sec["join_mode"])
    if mode not in MODES:
        return _fail("Mode must be off, open or approval.")
    code = sec["join_code"]
    if mode != "off" and (not code or data.get("regenerate") is True):
        code = people.new_join_code(db)                               # a new code stops the old one working at once
    elif data.get("regenerate") is True:
        code = people.new_join_code(db) if code else None
    db.execute("UPDATE sections SET join_mode = ?, join_code = ? WHERE id = ?", (mode, code, section_id))
    db.commit()
    return jsonify(_section_payload(db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()))


def _pending(db, teacher_id):
    return db.execute(
        """SELECT jr.id, jr.name, jr.roll_no, jr.email, jr.phone, jr.created_at, jr.user_id IS NOT NULL AS existing_login,
                  sec.id AS section_id, sec.name AS section_name, c.name AS class_name
           FROM join_requests jr JOIN sections sec ON sec.id = jr.section_id JOIN classes c ON c.id = sec.class_id
           WHERE c.teacher_id = ? ORDER BY jr.id""", (teacher_id,)).fetchall()


@teacher_bp.get("/requests")
@login_required("teacher")
def list_requests():
    rows = [dict(r) for r in _pending(get_db(), current_teacher()["id"])]
    return jsonify(requests=rows, count=len(rows))


def _own_request(db, teacher_id, request_id):
    for r in _pending(db, teacher_id):
        if r["id"] == request_id:
            return db.execute("SELECT * FROM join_requests WHERE id = ?", (request_id,)).fetchone()
    return None


@teacher_bp.post("/requests/<int:request_id>/approve")
@login_required("teacher")
def approve(request_id):
    db, t = get_db(), current_teacher()
    jr = _own_request(db, t["id"], request_id)
    if not jr:
        return _fail("Request not found.", 404)
    sec = own_section(db, t["id"], jr["section_id"])
    where = f"{sec['class_name']} - {sec['name']}"
    user_id = jr["user_id"]
    created_user = False
    if user_id is None:
        existing = db.execute("SELECT id, role FROM users WHERE email = ?", (jr["email"],)).fetchone()
        if existing and existing["role"] != "student":
            return _fail("That email now belongs to a teacher account. Reject this request.", 409)
        if existing:
            user_id = existing["id"]                       # they registered in the meantime: same person, their own password stays
        else:
            user_id = db.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'student')", (jr["email"], jr["password_hash"])).lastrowid
            created_user = True
    sid, err = people.add_enrollment(db, user_id, jr["section_id"], jr["roll_no"], jr["name"], jr["phone"], where)
    if err:
        db.rollback()
        return _fail(err, 409)
    db.execute("DELETE FROM join_requests WHERE id = ?", (request_id,))
    people.notify(db, user_id, "join", f"Your request to join {where} was approved.")
    db.commit()
    return jsonify(ok=True, student_id=sid, created_login=created_user)


@teacher_bp.post("/requests/<int:request_id>/reject")
@login_required("teacher")
def reject(request_id):
    db, t = get_db(), current_teacher()
    jr = _own_request(db, t["id"], request_id)
    if not jr:
        return _fail("Request not found.", 404)
    sec = own_section(db, t["id"], jr["section_id"])
    if jr["user_id"]:
        people.notify(db, jr["user_id"], "join", f"Your request to join {sec['class_name']} - {sec['name']} was declined.")
    db.execute("DELETE FROM join_requests WHERE id = ?", (request_id,))
    db.commit()
    return jsonify(ok=True)


# ================================================================ public (not logged in yet)
@public_bp.post("/preview")
def preview():
    sec, err = _look_up(get_db(), (request.get_json(silent=True) or {}).get("code"))
    if err:
        return err
    return jsonify(class_name=sec["class_name"], section_name=sec["section_name"], teacher_name=sec["teacher_name"], mode=sec["join_mode"])


def _clean_person(data):
    roll, err = clean_name(data.get("roll_no"), "Roll number", 30)
    if err: return None, err
    name, err = clean_name(data.get("name"), "Name", 80)
    if err: return None, err
    phone = (data.get("phone") or "").strip() if isinstance(data.get("phone"), str) else ""
    if len(phone) > 20:
        return None, "Phone number is too long."
    return {"roll_no": roll, "name": name, "phone": phone or None}, None


@public_bp.post("/signup")
def signup():
    """A brand-new student creates their own login and joins (or asks to join) a section."""
    db = get_db()
    data = request.get_json(silent=True) or {}
    sec, err = _look_up(db, data.get("code"))
    if err:
        return err
    p, perr = _clean_person(data)
    if perr:
        return _fail(perr)
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    if not EMAIL_RE.match(email) or len(email) > 120:
        return _fail("Enter a valid email address.")
    password = data.get("password")
    if not isinstance(password, str) or len(password) < 6:
        return _fail("Password must be at least 6 characters.")
    where = _where(sec)
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return _fail("That email already has an account. Log in first, then use “Join a class” on your dashboard.", 409)
    if db.execute("SELECT 1 FROM students WHERE section_id = ? AND roll_no = ?", (sec["id"], p["roll_no"])).fetchone():
        return _fail(f"Roll number {p['roll_no']} is already taken in {where}. Check it, or ask your teacher.", 409)
    if db.execute("SELECT 1 FROM join_requests WHERE section_id = ? AND (email = ? OR roll_no = ?)", (sec["id"], email, p["roll_no"])).fetchone():
        return _fail("A request with that email or roll number is already waiting for approval.", 409)
    try:
        if sec["join_mode"] == "approval":
            db.execute("INSERT INTO join_requests (section_id, name, roll_no, email, phone, password_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       (sec["id"], p["name"], p["roll_no"], email, p["phone"], generate_password_hash(password)))
            db.commit()
            return jsonify(status="pending", where=where), 202
        uid = db.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'student')", (email, generate_password_hash(password))).lastrowid
        _sid, err = people.add_enrollment(db, uid, sec["id"], p["roll_no"], p["name"], p["phone"], where)
        if err:
            db.rollback()
            return _fail(err, 409)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _fail("Could not join (that email or roll number is already used).", 409)
    session.clear()
    session["user_id"], session["role"] = uid, "student"
    return jsonify(status="joined", where=where), 201


# ================================================================ logged-in student joins one more class
@student_bp.post("/join")
@login_required("student")
def join_as_student():
    db = get_db()
    data = request.get_json(silent=True) or {}
    sec, err = _look_up(db, data.get("code"))
    if err:
        return err
    me = db.execute("SELECT u.email, st.name, st.phone FROM users u JOIN students st ON st.user_id = u.id WHERE u.id = ? ORDER BY st.id LIMIT 1",
                    (session["user_id"],)).fetchone()
    roll, rerr = clean_name(data.get("roll_no"), "Roll number", 30)
    if rerr:
        return _fail(rerr)
    where = _where(sec)
    if db.execute("SELECT 1 FROM students WHERE section_id = ? AND user_id = ?", (sec["id"], session["user_id"])).fetchone():
        return _fail(f"You are already in {where}.", 409)
    if db.execute("SELECT 1 FROM students WHERE section_id = ? AND roll_no = ?", (sec["id"], roll)).fetchone():
        return _fail(f"Roll number {roll} is already taken in {where}.", 409)
    if sec["join_mode"] == "approval":
        if db.execute("SELECT 1 FROM join_requests WHERE section_id = ? AND user_id = ?", (sec["id"], session["user_id"])).fetchone():
            return _fail("You already asked to join this section. Please wait for your teacher.", 409)
        db.execute("INSERT INTO join_requests (section_id, user_id, name, roll_no, email, phone) VALUES (?, ?, ?, ?, ?, ?)",
                   (sec["id"], session["user_id"], me["name"], roll, me["email"], me["phone"]))
        db.commit()
        return jsonify(status="pending", where=where), 202
    _sid, err = people.add_enrollment(db, session["user_id"], sec["id"], roll, me["name"], me["phone"], where)
    if err:
        db.rollback()
        return _fail(err, 409)
    db.commit()
    return jsonify(status="joined", where=where), 201


@student_bp.get("/notifications")
@login_required("student")
def notifications():
    db = get_db()
    rows = db.execute("SELECT id, kind, message, created_at, is_read FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 20",
                      (session["user_id"],)).fetchall()
    return jsonify(notifications=[dict(r) for r in rows], unread=sum(1 for r in rows if not r["is_read"]))


@student_bp.post("/notifications/read")
@login_required("student")
def notifications_read():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    db.commit()
    return jsonify(ok=True)
