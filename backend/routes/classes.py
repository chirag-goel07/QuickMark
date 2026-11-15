import sqlite3

from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services.ownership import clean_name, own_class, own_section, own_subject

bp = Blueprint("classes", __name__, url_prefix="/api/teacher")


def _fail(msg, code=400):
    return jsonify(error=msg), code


def _class_payload(db, c):
    sections = db.execute(
        """SELECT sec.id, sec.name, sec.join_mode, sec.join_code, COUNT(st.id) AS student_count
           FROM sections sec LEFT JOIN students st ON st.section_id = sec.id
           WHERE sec.class_id = ? GROUP BY sec.id ORDER BY sec.name""", (c["id"],)).fetchall()
    subjects = db.execute("SELECT id, name FROM subjects WHERE class_id = ? ORDER BY name", (c["id"],)).fetchall()
    return {"id": c["id"], "name": c["name"],
            "student_count": sum(s["student_count"] for s in sections),
            "sections": [dict(s) for s in sections],
            "subjects": [dict(s) for s in subjects]}


@bp.get("/classes")
@login_required("teacher")
def list_classes():
    db, t = get_db(), current_teacher()
    rows = db.execute("SELECT * FROM classes WHERE teacher_id = ? ORDER BY name", (t["id"],)).fetchall()
    return jsonify(classes=[_class_payload(db, c) for c in rows])


# ---------------- classes ----------------
@bp.post("/classes")
@login_required("teacher")
def add_class():
    db, t = get_db(), current_teacher()
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Class name")
    if err:
        return _fail(err)
    try:
        cur = db.execute("INSERT INTO classes (teacher_id, name) VALUES (?, ?)", (t["id"], name))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("You already have a class with that name.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], cur.lastrowid))), 201


@bp.put("/classes/<int:class_id>")
@login_required("teacher")
def edit_class(class_id):
    db, t = get_db(), current_teacher()
    if not own_class(db, t["id"], class_id):
        return _fail("Class not found.", 404)
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Class name")
    if err:
        return _fail(err)
    try:
        db.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("You already have a class with that name.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], class_id)))


@bp.delete("/classes/<int:class_id>")
@login_required("teacher")
def delete_class(class_id):
    db, t = get_db(), current_teacher()
    if not own_class(db, t["id"], class_id):
        return _fail("Class not found.", 404)
    n = db.execute(
        """SELECT COUNT(*) FROM students st JOIN sections sec ON sec.id = st.section_id
           WHERE sec.class_id = ?""", (class_id,)).fetchone()[0]
    if n:
        return _fail(f"This class still has {n} student(s). Move or delete them first.", 409)
    db.execute("DELETE FROM classes WHERE id = ?", (class_id,))   # sections + subjects cascade
    db.commit()
    return jsonify(ok=True)


# ---------------- sections ----------------
@bp.post("/classes/<int:class_id>/sections")
@login_required("teacher")
def add_section(class_id):
    db, t = get_db(), current_teacher()
    if not own_class(db, t["id"], class_id):
        return _fail("Class not found.", 404)
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Section name", 20)
    if err:
        return _fail(err)
    try:
        db.execute("INSERT INTO sections (class_id, name) VALUES (?, ?)", (class_id, name))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("This class already has that section.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], class_id))), 201


@bp.put("/sections/<int:section_id>")
@login_required("teacher")
def edit_section(section_id):
    db, t = get_db(), current_teacher()
    sec = own_section(db, t["id"], section_id)
    if not sec:
        return _fail("Section not found.", 404)
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Section name", 20)
    if err:
        return _fail(err)
    try:
        db.execute("UPDATE sections SET name = ? WHERE id = ?", (name, section_id))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("This class already has that section.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], sec["class_id"])))


@bp.delete("/sections/<int:section_id>")
@login_required("teacher")
def delete_section(section_id):
    db, t = get_db(), current_teacher()
    sec = own_section(db, t["id"], section_id)
    if not sec:
        return _fail("Section not found.", 404)
    n = db.execute("SELECT COUNT(*) FROM students WHERE section_id = ?", (section_id,)).fetchone()[0]
    if n:
        return _fail(f"This section still has {n} student(s). Move or delete them first.", 409)
    db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    db.commit()
    return jsonify(_class_payload(db, own_class(db, t["id"], sec["class_id"])))


# ---------------- subjects ----------------
@bp.post("/classes/<int:class_id>/subjects")
@login_required("teacher")
def add_subject(class_id):
    db, t = get_db(), current_teacher()
    if not own_class(db, t["id"], class_id):
        return _fail("Class not found.", 404)
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Subject name")
    if err:
        return _fail(err)
    try:
        db.execute("INSERT INTO subjects (class_id, name) VALUES (?, ?)", (class_id, name))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("This class already has that subject.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], class_id))), 201


@bp.put("/subjects/<int:subject_id>")
@login_required("teacher")
def edit_subject(subject_id):
    db, t = get_db(), current_teacher()
    sub = own_subject(db, t["id"], subject_id)
    if not sub:
        return _fail("Subject not found.", 404)
    name, err = clean_name((request.get_json(silent=True) or {}).get("name"), "Subject name")
    if err:
        return _fail(err)
    try:
        db.execute("UPDATE subjects SET name = ? WHERE id = ?", (name, subject_id))
        db.commit()
    except sqlite3.IntegrityError:
        return _fail("This class already has that subject.", 409)
    return jsonify(_class_payload(db, own_class(db, t["id"], sub["class_id"])))


@bp.delete("/subjects/<int:subject_id>")
@login_required("teacher")
def delete_subject(subject_id):
    db, t = get_db(), current_teacher()
    sub = own_subject(db, t["id"], subject_id)
    if not sub:
        return _fail("Subject not found.", 404)
    db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))   # old sessions keep their label
    db.commit()
    return jsonify(_class_payload(db, own_class(db, t["id"], sub["class_id"])))
