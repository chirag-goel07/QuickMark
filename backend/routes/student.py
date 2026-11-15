import time

from flask import Blueprint, abort, jsonify, request, session

from database.db import get_db
from middleware.auth import login_required
from services import realtime
from services import sessions as svc
from services import core, face, people, reports
from services.attendance_stats import student_overall

bp = Blueprint("student", __name__, url_prefix="/api/student")


_SELECT = """SELECT st.id, st.name, st.roll_no, st.phone, u.email, sec.id AS section_id, sec.name AS section_name, c.name AS class_name, c.id AS class_id,
                  t.warning_threshold, t.name AS teacher_name, t.require_face, u.must_change_password,
                  (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v,
                  (st.face_descriptor IS NOT NULL) AS face_enrolled, st.face_enrolled_at
           FROM students st JOIN users u ON u.id = st.user_id
           JOIN sections sec ON sec.id = st.section_id JOIN classes c ON c.id = sec.class_id
           JOIN teachers t ON t.id = c.teacher_id
           WHERE st.user_id = ? ORDER BY c.name, sec.name, st.id"""


def _enrollments(db):
    """Every class/section the logged-in student is in (taken from the server-side session, never from the request)."""
    rows = db.execute(_SELECT, (session["user_id"],)).fetchall()
    if not rows:
        abort(403)
    return rows


def _me(db):
    """The person-level details (name, picture, face, phone) - identical on every enrollment, so the first one is enough."""
    return _enrollments(db)[0]


def _ids(db):
    return [r["id"] for r in _enrollments(db)]


def _id_for_session(db, session_id):
    """Which of my enrollments belongs to this session (DSA-A, OOPS-B ...). Falls back to the first one,
    and the normal 'not available for you' checks then refuse it."""
    ids = _ids(db)
    s = svc.get_session(db, session_id) if session_id else None
    if s:
        for i in ids:
            if svc.is_eligible(db, s, i):
                return i
    return ids[0]


def _threshold(db):
    return min(r["warning_threshold"] for r in _enrollments(db))


@bp.get("/profile")
@login_required("student")
def profile():
    db = get_db()
    rows = _enrollments(db)
    me = rows[0]
    pct, present, total = student_overall(db, [r["id"] for r in rows])
    threshold = _threshold(db)
    return jsonify(name=me["name"], roll_no=", ".join(dict.fromkeys(r["roll_no"] for r in rows)), email=me["email"], phone=me["phone"] or "",
                   class_name=", ".join(dict.fromkeys(r["class_name"] for r in rows)),
                   section_name=", ".join(dict.fromkeys(r["section_name"] for r in rows)),
                   teacher_name=", ".join(dict.fromkeys(r["teacher_name"] for r in rows)),
                   enrollments=[{"class_name": r["class_name"], "section_name": r["section_name"], "roll_no": r["roll_no"],
                                 "teacher_name": r["teacher_name"]} for r in rows],
                   percentage=pct, present=present, total=total,
                   threshold=threshold, is_low=pct is not None and pct < threshold,
                   has_avatar=bool(me["has_avatar"]), avatar_v=me["avatar_v"], face_enrolled=bool(me["face_enrolled"]),
                   face_enrolled_at=me["face_enrolled_at"], require_face=any(r["require_face"] for r in rows),
                   needs_face_setup=any(r["require_face"] for r in rows) and not me["face_enrolled"],
                   must_change_password=bool(me["must_change_password"]))


@bp.get("/sessions/active")
@login_required("student")
def active_sessions():
    db, now = get_db(), time.time()
    ids = _ids(db)
    svc.expire_due_sessions(db, now)
    return jsonify(sessions=svc.students_open_sessions(db, ids, now))


@bp.get("/sessions/<int:session_id>")
@login_required("student")
def session_info(session_id):
    db, now = get_db(), time.time()
    me = {"id": _id_for_session(db, session_id)}
    svc.expire_due_sessions(db, now)
    s = svc.get_session(db, session_id)
    if not s or not svc.is_eligible(db, s, me["id"]):
        return jsonify(error="This attendance session is not available for you."), 403
    joined = db.execute("SELECT 1 FROM session_participants WHERE session_id = ? AND student_id = ?", (session_id, me["id"])).fetchone() is not None
    rec = db.execute("SELECT status FROM attendance_records WHERE session_id = ? AND student_id = ?", (session_id, me["id"])).fetchone()
    rq = db.execute("SELECT status FROM attendance_requests WHERE session_id = ? AND student_id = ?", (session_id, me["id"])).fetchone()
    return jsonify(id=s["id"], label=s["label"], type=s["session_type"], status=s["status"], joined=joined,
                   my_status=rec["status"] if rec else None, my_request=rq["status"] if rq else None,
                   face_required=svc.face_required(db, s), face_enrolled=face.enrolled_descriptor(db, me["id"]) is not None,
                   can_request=svc.requests_allowed_now(s) and (s["status"] != "ended" or (rec is not None and rec["status"] == "absent")) and rq is None
                               and not (rec is not None and rec["status"] == "present") and svc.request_window_open(s, now))


@bp.post("/sessions/<int:session_id>/join")
@login_required("student")
def join(session_id):
    db, now = get_db(), time.time()
    me = {"id": _id_for_session(db, session_id)}
    try:
        svc.expire_due_sessions(db, now)
        s, newly = svc.join_session(db, me["id"], session_id, now)
    except svc.SessionError as e:
        return jsonify(error=e.message, code=e.code), e.status
    if newly:
        realtime.push_state(db, session_id, now)           # teacher's waiting room updates live
    return jsonify(ok=True, already_joined=not newly, status=s["status"])


@bp.post("/attendance/scan")
@login_required("student")
def scan():
    db, now = get_db(), time.time()
    token = (request.get_json(silent=True) or {}).get("token")
    if not isinstance(token, str):
        return jsonify(error="No QR code received."), 400
    row = db.execute("SELECT session_id FROM qr_tokens WHERE token = ?", (token.strip(),)).fetchone()
    me = {"id": _id_for_session(db, row["session_id"] if row else None)}      # the enrollment that belongs to the scanned session
    try:
        s = svc.mark_attendance(db, me["id"], token.strip(), now)
    except svc.SessionError as e:
        return jsonify(error=e.message), e.status
    realtime.push_state(db, s["id"], now)
    return jsonify(ok=True, message="Attendance marked. You are present!", label=s["label"])


@bp.get("/attendance")
@login_required("student")
def my_attendance():
    """Only the logged-in student's own records, over all the classes they are in."""
    db = get_db()
    rows = _enrollments(db)
    ids = [r["id"] for r in rows]
    threshold = _threshold(db)
    pct, present, total = student_overall(db, ids)
    limit = request.args.get("limit", type=int)
    import config
    history = reports.student_history_rows(db, ids)
    month = time.strftime("%Y-%m")
    this_month = [h for h in history if h["date"].startswith(month)]
    streak = core.leading_streak([h["status"] == "present" for h in history])      # newest first: consecutive PRESENT sessions
    return jsonify(percentage=pct, present=present, total=total, absent=total - present, threshold=threshold, request_days=config.REQUEST_WINDOW_DAYS,
                   this_month={"present": sum(1 for h in this_month if h["status"] == "present"), "total": len(this_month)},
                   streak=streak, advice=reports.threshold_advice(present, total, threshold),
                   is_low=pct is not None and pct < threshold, class_name=", ".join(dict.fromkeys(r["class_name"] for r in rows)),
                   subjects=reports.student_subject_rows(db, ids),
                   history=history[:limit] if limit and limit > 0 else history)


@bp.get("/face")
@login_required("student")
def face_status():
    db = get_db()
    me = _me(db)
    return jsonify(enrolled=face.enrolled_descriptor(db, me["id"]) is not None)


@bp.post("/face/enroll")
@login_required("student")
def face_enroll():
    """First-time face enrollment: 3+ captures (128 numbers each) plus ONE small cropped photo, which becomes the
    profile picture. The student cannot change it afterwards (only a teacher's face reset allows a new one)."""
    from services.avatars import decode_photo
    db, now = get_db(), time.time()
    me = _me(db)
    data = request.get_json(silent=True) or {}
    photo = None
    if data.get("photo") is not None:
        photo, err = decode_photo(data.get("photo"))
        if err:
            return jsonify(error=err), 400
    try:
        face.enroll(db, me["id"], data.get("samples"), now, photo)
    except svc.SessionError as e:
        return jsonify(error=e.message, code=e.code), e.status
    return jsonify(ok=True)


@bp.post("/sessions/<int:session_id>/join-face")
@login_required("student")
def join_with_face(session_id):
    """Verify the face on the server, and only then join the waiting room."""
    db, now = get_db(), time.time()
    me = {"id": _id_for_session(db, session_id)}
    try:
        svc.expire_due_sessions(db, now)
        s, newly = svc.join_session(db, me["id"], session_id, now, (request.get_json(silent=True) or {}).get("descriptor"))
    except svc.SessionError as e:
        return jsonify(error=e.message, code=e.code), e.status
    if newly:
        realtime.push_state(db, session_id, now)
    return jsonify(ok=True, already_joined=not newly, status=s["status"])


@bp.post("/sessions/<int:session_id>/request")
@login_required("student")
def ask_teacher(session_id):
    """'I could not join / scan' -> ask the teacher to mark me present."""
    db, now = get_db(), time.time()
    me = {"id": _id_for_session(db, session_id)}
    try:
        svc.expire_due_sessions(db, now)
        s = svc.create_request(db, me["id"], session_id, (request.get_json(silent=True) or {}).get("message"), now)
    except svc.SessionError as e:
        return jsonify(error=e.message, code=e.code), e.status
    realtime.push_state(db, session_id, now)             # appears in the teacher's request list immediately
    return jsonify(ok=True)


# ------------------------------------------------------------------ profile, picture, settings
@bp.put("/profile")
@login_required("student")
def update_profile():
    """Students may change only their phone number here (name/roll/class are managed by the teacher)."""
    db = get_db()
    me = _me(db)
    phone = (request.get_json(silent=True) or {}).get("phone")
    phone = phone.strip() if isinstance(phone, str) else ""
    if len(phone) > 20:
        return jsonify(error="Phone number is too long."), 400
    people.set_person_columns(db, me["id"], phone=phone or None)
    db.commit()
    return jsonify(ok=True, phone=phone)


@bp.post("/password")
@login_required("student")
def change_password():
    from werkzeug.security import check_password_hash, generate_password_hash
    db = get_db()
    data = request.get_json(silent=True) or {}
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not check_password_hash(user["password_hash"], data.get("current_password") or ""):
        return jsonify(error="Your current password is wrong."), 400
    new = data.get("new_password")
    if not isinstance(new, str) or len(new) < 6:
        return jsonify(error="The new password must be at least 6 characters."), 400
    if check_password_hash(user["password_hash"], new):
        return jsonify(error="Choose a new password that is different from your current one."), 400
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (generate_password_hash(new), user["id"]))
    db.commit()
    return jsonify(ok=True)


@bp.get("/avatar")
@login_required("student")
def my_avatar():
    from services.avatars import avatar_response
    db = get_db()
    return avatar_response(db, _me(db)["id"])


_PICTURE_LOCKED = ("Your profile picture is the photo from your face setup and cannot be changed. "
                   "If it must be redone, ask your teacher to reset your face, then set it up again.")


@bp.post("/avatar")
@login_required("student")
def set_avatar():
    """Students can no longer upload a picture (it would let anyone use someone else's face)."""
    return jsonify(error=_PICTURE_LOCKED), 403


@bp.delete("/avatar")
@login_required("student")
def remove_avatar():
    return jsonify(error=_PICTURE_LOCKED), 403


# ------------------------------------------------------------------ classes, requests, export
@bp.get("/classes")
@login_required("student")
def my_classes():
    """Every class the student is enrolled in, each with its subjects + the student's attendance, and their groups."""
    db = get_db()
    out = []
    for me in _enrollments(db):
        subjects = [dict(r) for r in db.execute(
            """SELECT sub.id, sub.name, COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) AS present, COUNT(ar.student_id) AS total
               FROM subjects sub
               LEFT JOIN attendance_sessions s ON s.subject_id = sub.id AND s.status = 'ended'
               LEFT JOIN attendance_records ar ON ar.session_id = s.id AND ar.student_id = ?
               WHERE sub.class_id = ? GROUP BY sub.id ORDER BY sub.name""", (me["id"], me["class_id"])).fetchall()]
        general = [x for x in reports.student_subject_rows(db, me["id"]) if x["subject"] == "General"]
        for x in subjects:
            x["percentage"] = reports.pct(x["present"], x["total"])
        for g in general:                                  # sessions that were taken without choosing a subject
            subjects.append({"id": None, "name": "General (no subject)", "present": g["present"], "total": g["total"], "percentage": g["percentage"]})
        groups = [dict(r) for r in db.execute(
            """SELECT g.id, g.name, (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count
               FROM groups g JOIN group_members gm ON gm.group_id = g.id WHERE gm.student_id = ? ORDER BY g.name""", (me["id"],)).fetchall()]
        classmates = db.execute("SELECT COUNT(*) FROM students st JOIN sections sec ON sec.id = st.section_id WHERE sec.class_id = ?", (me["class_id"],)).fetchone()[0]
        out.append({"class_name": me["class_name"], "section_name": me["section_name"], "teacher_name": me["teacher_name"],
                    "students_in_class": classmates, "subjects": subjects, "groups": groups, "threshold": me["warning_threshold"]})
    return jsonify(classes=out, threshold=_threshold(db))


@bp.get("/requests")
@login_required("student")
def my_requests():
    db = get_db()
    ids = _ids(db)
    rows = db.execute(
        f"""SELECT rq.id, rq.status, rq.message, rq.created_at, rq.resolved_at, s.label, substr(COALESCE(s.started_at, s.created_at), 1, 10) AS date
           FROM attendance_requests rq JOIN attendance_sessions s ON s.id = rq.session_id
           WHERE rq.student_id IN ({",".join("?" * len(ids))}) ORDER BY rq.id DESC LIMIT 50""", ids).fetchall()
    return jsonify(requests=[dict(r) for r in rows])


@bp.get("/attendance/export.csv")
@login_required("student")
def my_attendance_csv():
    from services.csvutil import csv_response
    db = get_db()
    rows = reports.student_history_rows(db, _ids(db))
    return csv_response("my_attendance.csv", ["Date", "Class / Group", "Subject", "Status"],
                        [[r["date"], r["label"], r["subject"], r["status"]] for r in rows])
