import sqlite3

from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import groups as group_svc
from services.ownership import clean_name

bp = Blueprint("groups", __name__, url_prefix="/api/teacher/groups")

MAX_MEMBERS = 500


def _fail(msg, code=400):
    return jsonify(error=msg), code


def _own_group(db, teacher_id, group_id):
    return db.execute("SELECT * FROM groups WHERE id = ? AND teacher_id = ?", (group_id, teacher_id)).fetchone()


def _has_open_session(db, group_id):
    return db.execute("SELECT 1 FROM attendance_sessions WHERE group_id = ? AND status IN ('waiting', 'active')",
                      (group_id,)).fetchone() is not None


def _members(db, group_id):
    rows = db.execute(
        """SELECT st.id, st.name, st.roll_no, c.name AS class_name, sec.name AS section_name
           FROM group_members gm JOIN students st ON st.id = gm.student_id
           JOIN sections sec ON sec.id = st.section_id JOIN classes c ON c.id = sec.class_id
           WHERE gm.group_id = ? ORDER BY c.name, sec.name, st.roll_no""", (group_id,)).fetchall()
    return [dict(r) for r in rows]


def _group_payload(db, g):
    members = _members(db, g["id"])
    return {"id": g["id"], "name": g["name"], "member_count": len(members), "members": members,
            "sections": group_svc.sections_of(db, g["id"]), "by_sections": group_svc.is_section_group(db, g["id"]),
            "locked": _has_open_session(db, g["id"])}


def _clean_ids(db, teacher_id, raw):
    """Student ids must be a list of ints, all belonging to THIS teacher. Returns (ids, error)."""
    if not isinstance(raw, list):
        return None, "Select the students for this group."
    try:
        ids = sorted({int(x) for x in raw})
    except (TypeError, ValueError):
        return None, "Invalid student selection."
    if len(ids) > MAX_MEMBERS:
        return None, f"A group can have at most {MAX_MEMBERS} students."
    if ids:
        marks = ",".join("?" * len(ids))
        n = db.execute(
            f"""SELECT COUNT(*) FROM students st JOIN sections sec ON sec.id = st.section_id
                JOIN classes c ON c.id = sec.class_id WHERE c.teacher_id = ? AND st.id IN ({marks})""",
            [teacher_id] + ids).fetchone()[0]
        if n != len(ids):
            return None, "One or more selected students are not yours."
    return ids, None


def _clean_sections(db, teacher_id, raw):
    """Section ids must be a non-empty list of ints, all belonging to THIS teacher. Returns (ids, error)."""
    if not isinstance(raw, list) or not raw:
        return None, "Tick at least one section."
    try:
        ids = sorted({int(x) for x in raw})
    except (TypeError, ValueError):
        return None, "Invalid section selection."
    marks = ",".join("?" * len(ids))
    n = db.execute(f"""SELECT COUNT(*) FROM sections sec JOIN classes c ON c.id = sec.class_id
                       WHERE c.teacher_id = ? AND sec.id IN ({marks})""", [teacher_id] + ids).fetchone()[0]
    if n != len(ids):
        return None, "One or more selected sections are not yours."
    students = db.execute(f"SELECT COUNT(DISTINCT id) FROM students WHERE section_id IN ({marks})", ids).fetchone()[0]
    if students == 0:
        return None, "The ticked sections have no students yet."
    if students > MAX_MEMBERS:
        return None, f"A group can have at most {MAX_MEMBERS} students."
    return ids, None


def _save_members(db, teacher_id, group_id, data):
    """Section groups (data has section_ids): store the sections and fill members from them. Otherwise the old way: student_ids.
    Returns an error message or None. Does not commit."""
    if "section_ids" in data:
        ids, err = _clean_sections(db, teacher_id, data.get("section_ids"))
        if err:
            return err
        db.execute("DELETE FROM group_sections WHERE group_id = ?", (group_id,))
        db.executemany("INSERT INTO group_sections (group_id, section_id) VALUES (?, ?)", [(group_id, i) for i in ids])
        group_svc.sync_members(db, group_id)
        return None
    ids, err = _clean_ids(db, teacher_id, data.get("student_ids", []))
    if err:
        return err
    db.execute("DELETE FROM group_sections WHERE group_id = ?", (group_id,))
    db.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
    db.executemany("INSERT INTO group_members (group_id, student_id) VALUES (?, ?)", [(group_id, i) for i in ids])
    return None


@bp.get("")
@login_required("teacher")
def list_groups():
    db, t = get_db(), current_teacher()
    rows = db.execute(
        """SELECT g.id, g.name, EXISTS (SELECT 1 FROM attendance_sessions s WHERE s.group_id = g.id
                                        AND s.status IN ('waiting', 'active')) AS locked
           FROM groups g WHERE g.teacher_id = ? ORDER BY g.name""", (t["id"],)).fetchall()
    out = []
    for r in rows:
        locked = bool(r["locked"])
        if not locked:
            group_svc.sync_members(db, r["id"])          # section groups follow their sections (never during an open session)
        count = db.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ?", (r["id"],)).fetchone()[0]
        out.append({"id": r["id"], "name": r["name"], "member_count": count, "locked": locked,
                    "sections": group_svc.sections_of(db, r["id"])})
    db.commit()
    return jsonify(groups=out)


@bp.get("/<int:group_id>")
@login_required("teacher")
def get_group(group_id):
    db, t = get_db(), current_teacher()
    g = _own_group(db, t["id"], group_id)
    if not g:
        return _fail("Group not found.", 404)
    return jsonify(_group_payload(db, g))


@bp.post("")
@login_required("teacher")
def create_group():
    db, t = get_db(), current_teacher()
    data = request.get_json(silent=True) or {}
    name, err = clean_name(data.get("name"), "Group name")
    if err:
        return _fail(err)
    try:
        gid = db.execute("INSERT INTO groups (teacher_id, name) VALUES (?, ?)", (t["id"], name)).lastrowid
        err = _save_members(db, t["id"], gid, data)
        if err:
            db.rollback()
            return _fail(err)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _fail("You already have a group with that name.", 409)
    return jsonify(_group_payload(db, _own_group(db, t["id"], gid))), 201


@bp.put("/<int:group_id>")
@login_required("teacher")
def edit_group(group_id):
    db, t = get_db(), current_teacher()
    g = _own_group(db, t["id"], group_id)
    if not g:
        return _fail("Group not found.", 404)
    if _has_open_session(db, group_id):
        return _fail("This group has an open attendance session. End it before changing the group.", 409)
    data = request.get_json(silent=True) or {}
    name, err = clean_name(data.get("name"), "Group name")
    if err:
        return _fail(err)
    try:
        db.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
        err = _save_members(db, t["id"], group_id, data)
        if err:
            db.rollback()
            return _fail(err)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _fail("You already have a group with that name.", 409)
    return jsonify(_group_payload(db, _own_group(db, t["id"], group_id)))


@bp.delete("/<int:group_id>")
@login_required("teacher")
def delete_group(group_id):
    db, t = get_db(), current_teacher()
    if not _own_group(db, t["id"], group_id):
        return _fail("Group not found.", 404)
    if _has_open_session(db, group_id):
        return _fail("This group has an open attendance session. End it before deleting the group.", 409)
    db.execute("DELETE FROM groups WHERE id = ?", (group_id,))   # members go with it; old sessions keep their label
    db.commit()
    return jsonify(ok=True)
