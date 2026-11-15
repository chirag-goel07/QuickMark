import re
import sqlite3
from itertools import groupby

from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import core, emails, face, people, reports
from services.csvutil import csv_response
from services.attendance_stats import student_overall, student_percentages
from services.ownership import clean_name, own_section, own_student

bp = Blueprint("students", __name__, url_prefix="/api/teacher")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _fail(msg, code=400):
    return jsonify(error=msg), code


def _student_row(db, teacher, student_id):
    """One student in the same shape as the list, percentage included."""
    for s in _query_students(db, teacher):
        if s["id"] == student_id:
            return s
    return None


def _query_students(db, teacher, search="", class_id=None, section_id=None, low_only=False):
    sql = """SELECT st.id, st.roll_no, st.name, st.phone, u.email, (st.face_descriptor IS NOT NULL) AS face_enrolled, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v,
                    c.id AS class_id, c.name AS class_name, sec.id AS section_id, sec.name AS section_name
             FROM students st
             JOIN users u ON u.id = st.user_id
             JOIN sections sec ON sec.id = st.section_id
             JOIN classes c ON c.id = sec.class_id
             WHERE c.teacher_id = ?"""
    args = [teacher["id"]]
    if class_id:
        sql += " AND c.id = ?"; args.append(class_id)
    if section_id:
        sql += " AND sec.id = ?"; args.append(section_id)
    if search:
        like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (st.name LIKE ? ESCAPE '\\' OR st.roll_no LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\')"
        args += [like, like, like]
    sql += " ORDER BY c.name, sec.name, st.roll_no"

    pct = {p["student_id"]: p["percentage"] for p in student_percentages(db, teacher["id"])}
    out = []
    for r in db.execute(sql, args).fetchall():
        d = dict(r)
        d["face_enrolled"] = bool(r["face_enrolled"])
        d["has_avatar"] = bool(r["has_avatar"])
        d["percentage"] = pct.get(r["id"])          # None = no attendance recorded yet
        d["is_low"] = d["percentage"] is not None and d["percentage"] < teacher["warning_threshold"]
        if low_only and not d["is_low"]:
            continue
        if d["is_low"]:
            d["warning_subject"], d["warning_body"] = emails.warning_message(
                teacher["name"], d["name"], d["percentage"], teacher["warning_threshold"])
        out.append(d)
    # class -> section order from SQL; inside each section roll numbers in natural order (2 before 10) - C++ qm::NaturalKey
    return [d for _, grp in groupby(out, key=lambda d: d["section_id"]) for d in core.natural_sorted(list(grp), key=lambda d: d["roll_no"])]


def _validate(data, db, teacher, is_new):
    roll, err = clean_name(data.get("roll_no"), "Roll number", 30)
    if err: return None, err
    name, err = clean_name(data.get("name"), "Name", 80)
    if err: return None, err
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    if not EMAIL_RE.match(email) or len(email) > 120:
        return None, "Enter a valid email address."
    phone = (data.get("phone") or "").strip() if isinstance(data.get("phone"), str) else ""
    if len(phone) > 20:
        return None, "Phone number is too long."
    try:
        section_id = int(data.get("section_id"))
    except (TypeError, ValueError):
        return None, "Choose a class and section."
    sec = own_section(db, teacher["id"], section_id)
    if not sec:
        return None, "Choose a valid class and section."
    password = data.get("password") or ""
    if password and (not isinstance(password, str) or len(password) < 6):
        return None, "Password must be at least 6 characters."
    return {"roll_no": roll, "name": name, "email": email, "phone": phone or None, "section_id": section_id,
            "password": password, "where": f"{sec['class_name']} - {sec['name']}"}, None


def _check_roll_free(db, section_id, roll_no, where, ignore_student_id=None):
    row = db.execute("SELECT id FROM students WHERE section_id = ? AND roll_no = ?", (section_id, roll_no)).fetchone()
    if row and row["id"] != ignore_student_id:
        return f"Roll number {roll_no} is already used in {where}."
    return None


def enroll_student(db, teacher, v, default_password=None):
    """Adds one student to one section.  Returns (student_id, status, password, error).

    - brand-new email  -> a login is created (password given, else the batch default, else a random one)
    - email already belongs to a STUDENT -> the same person is simply added to this class too
      (their password, face and picture stay as they are; nothing about the other class is changed or shown)
    status: 'created' | 'enrolled'
    """
    user = db.execute("SELECT id, role FROM users WHERE email = ?", (v["email"],)).fetchone()
    if user and user["role"] != "student":
        return None, None, None, "That email belongs to a teacher account."
    err = _check_roll_free(db, v["section_id"], v["roll_no"], v["where"])
    if err:
        return None, None, None, err
    if user:
        if db.execute("SELECT 1 FROM students WHERE user_id = ? AND section_id = ?", (user["id"], v["section_id"])).fetchone():
            return None, None, None, f"This student is already in {v['where']}."
        sid = db.execute("INSERT INTO students (user_id, roll_no, name, phone, section_id) VALUES (?, ?, ?, ?, ?)",
                         (user["id"], v["roll_no"], v["name"], v["phone"], v["section_id"])).lastrowid
        people.copy_person_data(db, user["id"], sid)
        return sid, "enrolled", None, None
    password = v["password"] or default_password or people.random_password()
    uid = db.execute("INSERT INTO users (email, password_hash, role, must_change_password) VALUES (?, ?, 'student', 1)",
                     (v["email"], people.hash_new_password(password))).lastrowid
    sid = db.execute("INSERT INTO students (user_id, roll_no, name, phone, section_id) VALUES (?, ?, ?, ?, ?)",
                     (uid, v["roll_no"], v["name"], v["phone"], v["section_id"])).lastrowid
    return sid, "created", password, None


@bp.get("/students")
@login_required("teacher")
def list_students():
    db, t = get_db(), current_teacher()
    args = request.args
    rows = _query_students(
        db, t,
        search=(args.get("search") or "").strip(),
        class_id=args.get("class_id", type=int),
        section_id=args.get("section_id", type=int),
        low_only=args.get("low") == "1")
    return jsonify(students=rows, threshold=t["warning_threshold"])


@bp.get("/students/<int:student_id>/details")
@login_required("teacher")
def student_details(student_id):
    """Everything a teacher wants to see about ONE of their students: profile, overall %, subject-wise %, recent sessions."""
    db, t = get_db(), current_teacher()
    s = _student_row(db, t, student_id)
    if not s:
        return _fail("Student not found.", 404)
    pct, present, total = student_overall(db, student_id)
    threshold = t["warning_threshold"]
    history = reports.student_history_rows(db, student_id, limit=20)
    return jsonify(
        student={k: s[k] for k in ("id", "name", "roll_no", "email", "phone", "class_id", "class_name", "section_id", "section_name",
                                   "face_enrolled", "has_avatar", "avatar_v")},
        overall={"percentage": pct, "present": present, "absent": total - present, "total": total, "threshold": threshold,
                 "is_low": pct is not None and pct < threshold, "advice": reports.threshold_advice(present, total, threshold)},
        subjects=reports.student_subject_rows(db, student_id),
        history=[{k: h[k] for k in ("date", "label", "type", "subject", "status")} for h in history])


@bp.post("/students")
@login_required("teacher")
def add_student():
    db, t = get_db(), current_teacher()
    v, err = _validate(request.get_json(silent=True) or {}, db, t, is_new=True)
    if err:
        return _fail(err)
    try:
        sid, status, password, err = enroll_student(db, t, v)
        if err:
            db.rollback()
            return _fail(err, 409)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _fail("Could not save the student (that roll number or student is already in this section).", 409)
    out = _student_row(db, t, sid)
    out["status"] = status
    if status == "created" and not v["password"]:
        out["generated_password"] = password                  # shown to the teacher once
    return jsonify(out), 201


@bp.put("/students/<int:student_id>")
@login_required("teacher")
def edit_student(student_id):
    db, t = get_db(), current_teacher()
    st = own_student(db, t["id"], student_id)
    if not st:
        return _fail("Student not found.", 404)
    v, err = _validate(request.get_json(silent=True) or {}, db, t, is_new=False)
    if err:
        return _fail(err)
    err = _check_roll_free(db, v["section_id"], v["roll_no"], v["where"], ignore_student_id=student_id)
    if err:
        return _fail(err, 409)
    if v["section_id"] != st["section_id"] and db.execute(
            "SELECT 1 FROM students WHERE user_id = ? AND section_id = ?", (st["user_id"], v["section_id"])).fetchone():
        return _fail(f"This student is already in {v['where']}.", 409)
    email_changed = v["email"] != st["email"]
    login_change = email_changed or bool(v["password"])
    if login_change and people.teachers_of_user(db, st["user_id"]) != {t["id"]}:
        return _fail("This student is also in another teacher's class, so only the student can change the login email or password.", 403)
    if email_changed and db.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (v["email"], st["user_id"])).fetchone():
        return _fail("That email is already registered.", 409)
    try:
        db.execute("UPDATE students SET roll_no=?, name=?, section_id=? WHERE id=?",
                   (v["roll_no"], v["name"], v["section_id"], student_id))
        people.set_person_columns(db, student_id, phone=v["phone"])
        if email_changed:
            db.execute("UPDATE users SET email = ? WHERE id = ?", (v["email"], st["user_id"]))
        if v["password"]:                                   # blank = keep the old password
            db.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                       (people.hash_new_password(v["password"]), st["user_id"]))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _fail("Could not save the student (duplicate roll number or email).", 409)
    return jsonify(_student_row(db, t, student_id))


@bp.delete("/students/<int:student_id>")
@login_required("teacher")
def delete_student(student_id):
    """Removes the student from THIS teacher's class. The login is only deleted when it has no other class left."""
    db, t = get_db(), current_teacher()
    st = own_student(db, t["id"], student_id)
    if not st:
        return _fail("Student not found.", 404)
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))          # cascades to this class's records / group links
    if not db.execute("SELECT 1 FROM students WHERE user_id = ?", (st["user_id"],)).fetchone():
        db.execute("DELETE FROM users WHERE id = ?", (st["user_id"],))
    db.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- adding many students at once
MAX_BULK = 500


@bp.get("/students/template.csv")
@login_required("teacher")
def bulk_template():
    return csv_response("students_template.csv", ["roll_no", "name", "email", "phone", "password"],
                        [["1", "Asha Verma", "asha@college.edu", "9876500001", ""],
                         ["2", "Ravi Kumar", "ravi@college.edu", "", ""]])


@bp.post("/students/bulk")
@login_required("teacher")
def bulk_add():
    """Add a whole section at once from a CSV / pasted spreadsheet rows.

    Body: {section_id, default_password (optional), rows: [{roll_no, name, email, phone?, password?}, ...]}
    Every row is checked on its own: good rows are saved, bad rows come back with a reason (nothing else is affected).
    Rows without a password get `default_password`, or a random one. New logins must change it at first login.
    """
    db, t = get_db(), current_teacher()
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return _fail("There are no students to add.")
    if len(rows) > MAX_BULK:
        return _fail(f"Please add at most {MAX_BULK} students at a time.")
    try:
        section_id = int(data.get("section_id"))
    except (TypeError, ValueError):
        return _fail("Choose a class and section.")
    sec = own_section(db, t["id"], section_id)
    if not sec:
        return _fail("Choose a valid class and section.")
    default_pw = data.get("default_password") or ""
    if default_pw and (not isinstance(default_pw, str) or len(default_pw) < 6):
        return _fail("The common password must be at least 6 characters.")

    results, created, enrolled, failed = [], 0, 0, 0
    for i, raw in enumerate(rows, start=1):
        raw = raw if isinstance(raw, dict) else {}
        item = {"row": i, "roll_no": str(raw.get("roll_no") or "").strip(), "name": str(raw.get("name") or "").strip(),
                "email": str(raw.get("email") or "").strip().lower()}
        v, err = _validate({**raw, "roll_no": raw.get("roll_no") and str(raw.get("roll_no")), "section_id": section_id}, db, t, is_new=True)
        if not err:
            db.execute("SAVEPOINT bulk_row")
            try:
                sid, status, password, err = enroll_student(db, t, v, default_pw or None)
            except sqlite3.IntegrityError:
                sid, status, password, err = None, None, None, "Duplicate roll number or student."
            if err:
                db.execute("ROLLBACK TO bulk_row")
            db.execute("RELEASE bulk_row")
        if err:
            failed += 1
            results.append({**item, "status": "error", "message": err})
            continue
        if status == "created":
            created += 1
            results.append({**item, "status": "created", "password": password})
        else:
            enrolled += 1
            results.append({**item, "status": "enrolled", "message": "Already has a QuickMark login - added to this class."})
    db.commit()
    return jsonify(created=created, enrolled=enrolled, failed=failed, section=f"{sec['class_name']} - {sec['name']}", results=results)


@bp.post("/students/<int:student_id>/reset-password")
@login_required("teacher")
def reset_password(student_id):
    """A student forgot their password: give them a new random one (shown to the teacher once). They can change it after logging in."""
    db, t = get_db(), current_teacher()
    st = own_student(db, t["id"], student_id)
    if not st:
        return _fail("Student not found.", 404)
    if people.teachers_of_user(db, st["user_id"]) != {t["id"]}:
        return _fail("This student is also in another teacher's class, so only the student can reset their password (use Forgot password).", 403)
    password = people.random_password()
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?", (people.hash_new_password(password), st["user_id"]))
    db.commit()
    return jsonify(password=password, email=st["email"], name=st["name"])


@bp.post("/students/<int:student_id>/reset-face")
@login_required("teacher")
def reset_face(student_id):
    """Forget the student's face template so they can enroll again (e.g. wrong person enrolled, new look)."""
    db, t = get_db(), current_teacher()
    if not own_student(db, t["id"], student_id):
        return _fail("Student not found.", 404)
    face.reset(db, student_id)
    return jsonify(ok=True)


@bp.get("/students/<int:student_id>/avatar")
@login_required("teacher")
def student_avatar(student_id):
    """A teacher can see the small profile picture of their OWN students (shown next to requests and in lists)."""
    from services.avatars import avatar_response
    db, t = get_db(), current_teacher()
    if not own_student(db, t["id"], student_id):
        return _fail("Student not found.", 404)
    return avatar_response(db, student_id)
