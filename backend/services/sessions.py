"""Attendance session logic shared by NORMAL (section) and GROUP attendance.

Life cycle:  waiting  --start-->  active  --end / time runs out-->  ended
            (waiting room,        (QR shown,                        (absent rows written,
             no QR exists)         students scan)                    counted in history)
Every function takes the db connection and "now" (unix seconds) so it can be tested exactly.
"""
import secrets
import sqlite3
from datetime import datetime

import config
from services import core

FMT = "%Y-%m-%d %H:%M:%S"


class SessionError(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def ts_to_str(ts):
    return datetime.fromtimestamp(ts).strftime(FMT)


def str_to_ts(text):
    return datetime.strptime(text, FMT).timestamp()


# ---------------------------------------------------------------- lookups
def get_session(db, session_id):
    return db.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()


def eligible_ids(db, s):
    if s["session_type"] == "normal":
        rows = db.execute("SELECT id FROM students WHERE section_id = ?", (s["section_id"],)).fetchall()
    else:
        rows = db.execute("SELECT student_id AS id FROM group_members WHERE group_id = ?", (s["group_id"],)).fetchall()
    return [r["id"] for r in rows]


def is_eligible(db, s, student_id):
    return student_id in set(eligible_ids(db, s))


def expires_at(s):
    """Unix time when an ACTIVE session runs out (None while waiting)."""
    if not s["started_at"]:
        return None
    return str_to_ts(s["started_at"]) + s["duration_minutes"] * 60


def open_session_for_teacher(db, teacher_id):
    return db.execute(
        "SELECT * FROM attendance_sessions WHERE teacher_id = ? AND status IN ('waiting', 'active') ORDER BY id DESC LIMIT 1",
        (teacher_id,)).fetchone()


# ---------------------------------------------------------------- create / start / end
def create_normal_session(db, teacher, section_id, subject_id, duration_minutes, now):
    sec = db.execute(
        """SELECT sec.id, sec.name, c.id AS class_id, c.name AS class_name FROM sections sec
           JOIN classes c ON c.id = sec.class_id WHERE sec.id = ? AND c.teacher_id = ?""",
        (section_id, teacher["id"])).fetchone()
    if not sec:
        raise SessionError("Choose a valid class and section.", 400)
    label = f"{sec['class_name']} - {sec['name']}"
    if subject_id:
        sub = db.execute("SELECT name FROM subjects WHERE id = ? AND class_id = ?", (subject_id, sec["class_id"])).fetchone()
        if not sub:
            raise SessionError("That subject does not belong to this class.", 400)
        label += f" ({sub['name']})"
    else:
        subject_id = None
    total = db.execute("SELECT COUNT(*) FROM students WHERE section_id = ?", (section_id,)).fetchone()[0]
    if total == 0:
        raise SessionError("This section has no students yet. Add students first.", 400)
    return _insert_session(db, teacher, "normal", section_id, None, subject_id, label, total, duration_minutes, now)


def create_group_session(db, teacher, group_id, duration_minutes, now):
    g = db.execute("SELECT * FROM groups WHERE id = ? AND teacher_id = ?", (group_id, teacher["id"])).fetchone()
    if not g:
        raise SessionError("Choose a valid group.", 400)
    if not open_session_for_teacher(db, teacher["id"]):
        from services import groups as group_svc
        group_svc.sync_members(db, group_id)            # students who joined/left the ticked sections since the group was saved
        db.commit()
    total = db.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,)).fetchone()[0]
    if total == 0:
        raise SessionError("This group has no students yet.", 400)
    return _insert_session(db, teacher, "group", None, group_id, None, f"Group: {g['name']}", total, duration_minutes, now)


def _insert_session(db, teacher, kind, section_id, group_id, subject_id, label, total, duration_minutes, now):
    if open_session_for_teacher(db, teacher["id"]):
        raise SessionError("You already have an open attendance session. Resume or end it first.", 409)
    try:
        duration = int(duration_minutes if duration_minutes is not None else teacher["session_minutes"])
    except (TypeError, ValueError):
        raise SessionError("Duration must be a number of minutes.", 400)
    if not 1 <= duration <= 180:
        raise SessionError("Duration must be between 1 and 180 minutes.", 400)
    cur = db.execute(
        """INSERT INTO attendance_sessions (teacher_id, session_type, section_id, group_id, subject_id, label,
                                            status, duration_minutes, total_students, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?, ?, ?)""",
        (teacher["id"], kind, section_id, group_id, subject_id, label, duration, total, ts_to_str(now)))
    db.commit()
    return cur.lastrowid


def start_session(db, session_id, now):
    """Waiting room -> actual attendance. Only now does a QR token come into existence."""
    cur = db.execute("UPDATE attendance_sessions SET status = 'active', started_at = ? WHERE id = ? AND status = 'waiting'",
                     (ts_to_str(now), session_id))
    if cur.rowcount == 0:
        db.rollback()
        raise SessionError("This session has already been started or ended.", 409)
    db.commit()
    return issue_token(db, session_id, now)


def finalize_session(db, session_id, now):
    """End an ACTIVE session: everyone eligible who did not scan becomes 'absent'. Safe to call twice."""
    cur = db.execute("UPDATE attendance_sessions SET status = 'ended', ended_at = ? WHERE id = ? AND status = 'active'",
                     (ts_to_str(now), session_id))
    if cur.rowcount == 0:
        db.rollback()
        return False                                   # someone else already ended it
    s = get_session(db, session_id)
    ids = eligible_ids(db, s)
    db.executemany("INSERT OR IGNORE INTO attendance_records (session_id, student_id, status) VALUES (?, ?, 'absent')",
                   [(session_id, i) for i in ids])
    db.execute("UPDATE attendance_sessions SET total_students = ? WHERE id = ?", (len(ids), session_id))
    db.execute("DELETE FROM qr_tokens WHERE session_id = ?", (session_id,))      # no more scans possible
    db.commit()
    from services import alerts                                                  # low-attendance notices (never blocks ending)
    alerts.safe_after_session(db, session_id, now)
    return True


def cancel_waiting_session(db, session_id):
    cur = db.execute("DELETE FROM attendance_sessions WHERE id = ? AND status = 'waiting'", (session_id,))
    db.commit()
    if cur.rowcount == 0:
        raise SessionError("Only a session that has not started can be cancelled.", 409)


def expire_due_sessions(db, now):
    """Ends active sessions whose time ran out. Returns the ids that were ended."""
    ended = []
    for s in db.execute("SELECT * FROM attendance_sessions WHERE status = 'active'").fetchall():
        exp = expires_at(s)
        if exp is not None and now >= exp and finalize_session(db, s["id"], now):
            ended.append(s["id"])
    return ended


# ---------------------------------------------------------------- QR tokens (server side only)
def issue_token(db, session_id, now):
    token = secrets.token_urlsafe(12)
    db.execute("INSERT INTO qr_tokens (token, session_id, expires_at) VALUES (?, ?, ?)",
               (token, session_id, now + config.TOKEN_LIFETIME))
    db.execute("DELETE FROM qr_tokens WHERE session_id = ? AND expires_at < ?", (session_id, now - 10))
    db.commit()
    return token


def latest_token(db, session_id, now):
    row = db.execute("SELECT token FROM qr_tokens WHERE session_id = ? AND expires_at >= ? ORDER BY expires_at DESC LIMIT 1",
                     (session_id, now)).fetchone()
    return row["token"] if row else None


# ---------------------------------------------------------------- students: join + scan
def join_session(db, student_id, session_id, now, descriptor=None):
    """Join the waiting room. If the teacher requires face verification, the face must match first."""
    s = get_session(db, session_id)
    if not s or not is_eligible(db, s, student_id):
        raise SessionError("This attendance session is not available for you.", 403)
    if s["status"] == "ended" or (s["status"] == "active" and expires_at(s) <= now):
        raise SessionError("This attendance session has ended.", 409)
    if face_required(db, s):
        if descriptor is None:
            raise SessionError("Face verification is required to join this session.", 403, "face_required")
        from services import face                      # imported here to avoid a circular import
        face.verify(db, student_id, descriptor, now)
    cur = db.execute("INSERT OR IGNORE INTO session_participants (session_id, student_id, joined_at) VALUES (?, ?, ?)",
                     (session_id, student_id, ts_to_str(now)))
    db.commit()
    return s, cur.rowcount == 1          # (session, newly_joined?)


def face_required(db, s):
    row = db.execute("SELECT require_face FROM teachers WHERE id = ?", (s["teacher_id"],)).fetchone()
    return bool(row and row["require_face"])


def mark_attendance(db, student_id, token, now):
    """Everything is validated here on the server: token, expiry, session state, eligibility, duplicates."""
    row = db.execute("SELECT session_id, expires_at FROM qr_tokens WHERE token = ?", (token or "",)).fetchone()
    if not row or row["expires_at"] < now:
        raise SessionError("This QR code has expired. Scan the code that is showing now.", 400)
    s = get_session(db, row["session_id"])
    if s["status"] != "active":
        raise SessionError("Attendance is not running for this session.", 409)
    exp = expires_at(s)
    if now >= exp:
        finalize_session(db, s["id"], now)
        raise SessionError("This attendance session has ended.", 409)
    if not is_eligible(db, s, student_id):
        raise SessionError("You are not part of this attendance session.", 403)
    joined = db.execute("SELECT 1 FROM session_participants WHERE session_id = ? AND student_id = ?",
                        (s["id"], student_id)).fetchone()
    if not joined:
        raise SessionError("Join the session before scanning.", 403)
    try:
        db.execute("INSERT INTO attendance_records (session_id, student_id, status, marked_at, marked_via) VALUES (?, ?, 'present', ?, 'qr')",
                   (s["id"], student_id, ts_to_str(now)))
        _cancel_pending_request(db, s["id"], student_id, now)
        db.commit()
    except sqlite3.IntegrityError:                     # primary key (session, student) = duplicate
        db.rollback()
        raise SessionError("Your attendance is already marked for this session.", 409)
    return s


# ---------------------------------------------------------------- the ONE place attendance records are changed by a teacher
def _cancel_pending_request(db, session_id, student_id, now):
    db.execute("UPDATE attendance_requests SET status = 'cancelled', resolved_at = ? WHERE session_id = ? AND student_id = ? AND status = 'pending'",
               (ts_to_str(now), session_id, student_id))


def _write_record(db, s, student_id, status, via, now, teacher_id, kind="edit"):
    """Set one student's status in one session and log the change. Does not commit."""
    old = db.execute("SELECT status FROM attendance_records WHERE session_id = ? AND student_id = ?",
                     (s["id"], student_id)).fetchone()
    old_status = old["status"] if old else None
    if status == "absent" and s["status"] != "ended":
        # while a session is running 'absent' just means "not marked yet": remove the row
        db.execute("DELETE FROM attendance_records WHERE session_id = ? AND student_id = ?", (s["id"], student_id))
        new_status = None
    else:
        db.execute("""INSERT INTO attendance_records (session_id, student_id, status, marked_at, marked_via) VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT (session_id, student_id) DO UPDATE SET status = excluded.status,
                      marked_at = excluded.marked_at, marked_via = excluded.marked_via""",
                   (s["id"], student_id, status, ts_to_str(now), via))
        new_status = status
    if status == "present":
        _cancel_pending_request(db, s["id"], student_id, now)
    if old_status != new_status:
        db.execute("INSERT INTO attendance_edits (session_id, student_id, teacher_id, old_status, new_status, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (s["id"], student_id, teacher_id, old_status, new_status, kind, ts_to_str(now)))
    if s["status"] == "ended":      # keep the saved total right if a student without a record was added
        n = db.execute("SELECT COUNT(*) FROM attendance_records WHERE session_id = ?", (s["id"],)).fetchone()[0]
        db.execute("UPDATE attendance_sessions SET total_students = ? WHERE id = ?", (n, s["id"]))


def teacher_set_attendance(db, s, student_id, status, now, teacher_id, allowed_states):
    """Manual edit by the teacher: while the session runs ('active') or after it ended ('ended')."""
    if status not in ("present", "absent"):
        raise SessionError("Status must be present or absent.", 400)
    if s["status"] not in allowed_states:
        raise SessionError("Attendance cannot be edited in this state." if s["status"] == "waiting"
                           else "This session is not in a state that allows that edit.", 409)
    if not is_eligible(db, s, student_id):
        raise SessionError("That student is not part of this session.", 400)
    _write_record(db, s, student_id, status, "teacher", now, teacher_id)
    db.commit()


def requests_allowed_now(s):
    """By default requests are only possible after the session has ended."""
    return s["status"] == "ended" or config.REQUESTS_DURING_SESSION


def request_window_open(s, now):
    """Requests are possible while the session is open and for REQUEST_WINDOW_DAYS days after it ended."""
    if s["status"] != "ended":
        return True
    ended = str_to_ts(s["ended_at"]) if s["ended_at"] else 0
    return now - ended <= config.REQUEST_WINDOW_DAYS * 86400


def create_request(db, student_id, session_id, message, now):
    """A student who could not join or scan (during the session OR after it ended) asks the teacher to mark them present."""
    s = get_session(db, session_id)
    if not s or not is_eligible(db, s, student_id):
        raise SessionError("This attendance session is not available for you.", 403)
    if not requests_allowed_now(s):
        raise SessionError("Requests can be sent after the session has ended. Open My Attendance and use Request correction.", 409, "after_session_only")
    if not request_window_open(s, now):
        raise SessionError(f"The {config.REQUEST_WINDOW_DAYS}-day period for asking about this session has passed. Please speak to your teacher.", 409)
    if db.execute("SELECT 1 FROM attendance_records WHERE session_id = ? AND student_id = ? AND status = 'present'",
                  (session_id, student_id)).fetchone():
        raise SessionError("You are already marked present.", 409)
    prev = db.execute("SELECT status FROM attendance_requests WHERE session_id = ? AND student_id = ?", (session_id, student_id)).fetchone()
    if prev:
        raise SessionError({"pending": "You already sent a request. Please wait for your teacher.",
                            "approved": "Your request was already approved.",
                            "rejected": "Your teacher declined your request.",
                            "cancelled": "You are already marked present."}[prev["status"]], 409)
    msg = message.strip() if isinstance(message, str) else ""
    if len(msg) > 200:
        raise SessionError("Please keep your message under 200 characters.", 400)
    db.execute("INSERT INTO attendance_requests (session_id, student_id, message, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
               (session_id, student_id, msg or None, ts_to_str(now)))
    db.commit()
    return s


def resolve_request(db, teacher_id, request_id, accept, now):
    """Teacher accepts (student becomes present) or rejects. Works while waiting, running or after the session."""
    r = db.execute("""SELECT rq.*, s.teacher_id FROM attendance_requests rq JOIN attendance_sessions s ON s.id = rq.session_id
                      WHERE rq.id = ?""", (request_id,)).fetchone()
    if not r or r["teacher_id"] != teacher_id:
        raise SessionError("Request not found.", 404)
    if r["status"] != "pending":
        raise SessionError("This request was already handled.", 409)
    s = get_session(db, r["session_id"])
    if accept:
        if s["status"] != "ended":                      # counts as having joined the waiting room
            db.execute("INSERT OR IGNORE INTO session_participants (session_id, student_id, joined_at) VALUES (?, ?, ?)",
                       (s["id"], r["student_id"], ts_to_str(now)))
        _write_record(db, s, r["student_id"], "present", "request", now, teacher_id, kind="request")
    db.execute("UPDATE attendance_requests SET status = ?, resolved_at = ? WHERE id = ?",
               ("approved" if accept else "rejected", ts_to_str(now), request_id))
    db.commit()
    return s


def _rows(rows):
    """Dicts for JSON, with the avatar flag as a real true/false."""
    out = []
    for r in rows:
        d = dict(r)
        if "has_avatar" in d:
            d["has_avatar"] = bool(d["has_avatar"])
        out.append(d)
    return out


def pending_requests_for_teacher(db, teacher_id, limit=50):
    """Every request still waiting for this teacher (running sessions and finished ones)."""
    rows = db.execute(
        """SELECT rq.id, rq.session_id, rq.student_id, rq.message, rq.created_at, st.name, st.roll_no,
                  (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v,
                  s.label, s.status AS session_status, substr(COALESCE(s.started_at, s.created_at), 1, 10) AS date
           FROM attendance_requests rq JOIN attendance_sessions s ON s.id = rq.session_id
           JOIN students st ON st.id = rq.student_id
           WHERE s.teacher_id = ? AND rq.status = 'pending' ORDER BY rq.id DESC LIMIT ?""", (teacher_id, limit)).fetchall()
    return _rows(rows)


# ---------------------------------------------------------------- state sent to the teacher screen
def build_state(db, s, now):
    sid = s["id"]
    ended = s["status"] == "ended"
    total = s["total_students"] if ended else len(eligible_ids(db, s))
    joined = db.execute(
        """SELECT st.id, st.name, st.roll_no, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v FROM session_participants sp JOIN students st ON st.id = sp.student_id
           WHERE sp.session_id = ? ORDER BY sp.joined_at, st.name""", (sid,)).fetchall()
    present = db.execute(
        """SELECT st.id, st.name, st.roll_no, ar.marked_via AS via, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v FROM attendance_records ar JOIN students st ON st.id = ar.student_id
           WHERE ar.session_id = ? AND ar.status = 'present' ORDER BY ar.marked_at""", (sid,)).fetchall()
    requests = db.execute(
        """SELECT rq.id, rq.student_id, st.name, st.roll_no, rq.message, rq.created_at, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v FROM attendance_requests rq
           JOIN students st ON st.id = rq.student_id WHERE rq.session_id = ? AND rq.status = 'pending' ORDER BY rq.id""", (sid,)).fetchall()
    state = {
        "id": sid, "label": s["label"], "type": s["session_type"], "status": s["status"],
        "duration_minutes": s["duration_minutes"], "total": total,
        "joined": len(joined), "joined_pct": round(100.0 * len(joined) / total) if total else 0,
        "joined_students": _rows(joined),
        "present": len(present), "present_students": _rows(present),
        "requests": _rows(requests),
        "server_time": now, "expires_at": None, "remaining_seconds": None,
    }
    if s["status"] == "active":
        exp = expires_at(s)
        state["expires_at"] = exp
        state["remaining_seconds"] = max(0, int(exp - now))
    if ended:
        absent = db.execute(
            """SELECT st.id, st.name, st.roll_no, ar.marked_via AS via, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v FROM attendance_records ar JOIN students st ON st.id = ar.student_id
               WHERE ar.session_id = ? AND ar.status = 'absent' ORDER BY st.roll_no""", (sid,)).fetchall()
        state["absent"] = len(absent)
        state["absent_students"] = _rows(absent)
        state["present_pct"] = round(100.0 * len(present) / total) if total else 0
        state["sections"] = section_boxes(db, sid)
    return state


def section_boxes(db, session_id):
    """Everyone with a record in an ENDED session, split into one box per class/section (used by 'Edit attendance')."""
    rows = db.execute(
        """SELECT st.id, st.name, st.roll_no, ar.status, ar.marked_via AS via, (st.avatar IS NOT NULL) AS has_avatar, st.avatar_updated_at AS avatar_v,
                  sec.id AS section_id, sec.name AS section_name, c.name AS class_name
           FROM attendance_records ar JOIN students st ON st.id = ar.student_id
           JOIN sections sec ON sec.id = st.section_id JOIN classes c ON c.id = sec.class_id
           WHERE ar.session_id = ? ORDER BY c.name, sec.name, st.roll_no""", (session_id,)).fetchall()
    boxes = {}
    for r in _rows(rows):
        b = boxes.setdefault(r["section_id"], {"section_id": r["section_id"], "label": f"{r['class_name']} - {r['section_name']}",
                                                "students": [], "present": 0, "absent": 0})
        b["students"].append({k: r[k] for k in ("id", "name", "roll_no", "status", "via", "has_avatar", "avatar_v")})
        b["present" if r["status"] == "present" else "absent"] += 1
    out = list(boxes.values())
    for b in out:                                       # natural order of roll numbers: 2 before 10
        b["students"] = core.natural_sorted(b["students"], key=lambda x: x["roll_no"])      # C++ qm::NaturalKey
    return out


def students_open_sessions(db, student_ids, now):
    """Waiting/active sessions this person may join (normal: any of their sections, group: member).
    A person can have several enrollments (DSA, OOPS ...), so this takes one id or a list of ids."""
    ids = [student_ids] if isinstance(student_ids, int) else list(student_ids)
    seen, out = set(), []
    for student_id in ids:
        rows = db.execute(
            """SELECT s.*, t.name AS teacher_name FROM attendance_sessions s
               JOIN teachers t ON t.id = s.teacher_id
               WHERE s.status IN ('waiting', 'active') AND (
                     (s.session_type = 'normal' AND s.section_id = (SELECT section_id FROM students WHERE id = ?))
                  OR (s.session_type = 'group' AND s.group_id IN (SELECT group_id FROM group_members WHERE student_id = ?)))
               ORDER BY s.id DESC""", (student_id, student_id)).fetchall()
        for s in rows:
            if s["id"] in seen:
                continue
            if s["status"] == "active" and expires_at(s) <= now:
                continue                                   # ran out; the background task will finalize it
            seen.add(s["id"])
            joined = db.execute("SELECT 1 FROM session_participants WHERE session_id = ? AND student_id = ?",
                                (s["id"], student_id)).fetchone() is not None
            marked = db.execute("SELECT 1 FROM attendance_records WHERE session_id = ? AND student_id = ? AND status = 'present'",
                                (s["id"], student_id)).fetchone() is not None
            out.append({"id": s["id"], "label": s["label"], "type": s["session_type"], "status": s["status"],
                        "teacher_name": s["teacher_name"], "joined": joined, "marked": marked})
    out.sort(key=lambda x: -x["id"])
    return out
