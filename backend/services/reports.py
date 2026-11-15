"""Report and history queries. Percentages are always calculated here on the server."""
import re

from services import core

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def pct(present, total):
    return core.percent(present, total)                     # C++: qm::AttendanceStats::percentage


def _ended_ids_sql():
    return "SELECT id FROM attendance_sessions WHERE teacher_id = ? AND status = 'ended'"


def history_rows(db, teacher_id, class_id=None, kind=None, date_from=None, date_to=None):
    sql = """SELECT s.id, s.label, s.session_type AS type, s.started_at, s.ended_at, s.total_students AS total,
                    sub.name AS subject,
                    (SELECT COUNT(*) FROM attendance_requests rq WHERE rq.session_id = s.id AND rq.status = 'pending') AS pending_requests,
                    COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) AS present
             FROM attendance_sessions s
             LEFT JOIN attendance_records ar ON ar.session_id = s.id
             LEFT JOIN subjects sub ON sub.id = s.subject_id
             LEFT JOIN sections sec ON sec.id = s.section_id
             WHERE s.teacher_id = ? AND s.status = 'ended'"""
    args = [teacher_id]
    if class_id:
        sql += " AND sec.class_id = ?"; args.append(class_id)
    if kind in ("normal", "group"):
        sql += " AND s.session_type = ?"; args.append(kind)
    if date_from and DATE_RE.match(date_from):
        sql += " AND date(s.started_at) >= ?"; args.append(date_from)
    if date_to and DATE_RE.match(date_to):
        sql += " AND date(s.started_at) <= ?"; args.append(date_to)
    sql += " GROUP BY s.id ORDER BY s.started_at DESC, s.id DESC"
    out = []
    for r in db.execute(sql, args).fetchall():
        d = dict(r)
        d["absent"] = d["total"] - d["present"]
        d["percentage"] = pct(d["present"], d["total"])
        d["date"] = (d["started_at"] or "")[:10]
        out.append(d)
    return out


def student_rows(db, teacher_id):
    """Every student of this teacher with present/total (None percentage = nothing recorded yet)."""
    rows = db.execute(
        f"""SELECT st.id, st.roll_no, st.name, u.email, c.name AS class_name, sec.name AS section_name,
                   COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) AS present,
                   COUNT(ar.student_id) AS total
            FROM students st JOIN users u ON u.id = st.user_id JOIN sections sec ON sec.id = st.section_id JOIN classes c ON c.id = sec.class_id
            LEFT JOIN attendance_records ar ON ar.student_id = st.id AND ar.session_id IN ({_ended_ids_sql()})
            WHERE c.teacher_id = ? GROUP BY st.id ORDER BY c.name, sec.name, st.roll_no""",
        (teacher_id, teacher_id)).fetchall()
    return [{**dict(r), "percentage": pct(r["present"], r["total"])} for r in rows]


def class_rows(db, teacher_id):
    rows = db.execute(
        f"""SELECT c.id, c.name, COUNT(DISTINCT st.id) AS students,
                   COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) AS present, COUNT(ar.student_id) AS total
            FROM classes c LEFT JOIN sections sec ON sec.class_id = c.id LEFT JOIN students st ON st.section_id = sec.id
            LEFT JOIN attendance_records ar ON ar.student_id = st.id AND ar.session_id IN ({_ended_ids_sql()})
            WHERE c.teacher_id = ? GROUP BY c.id ORDER BY c.name""", (teacher_id, teacher_id)).fetchall()
    return [{**dict(r), "percentage": pct(r["present"], r["total"])} for r in rows]


def section_rows(db, teacher_id):
    rows = db.execute(
        f"""SELECT sec.id, c.name AS class_name, sec.name AS section_name, COUNT(DISTINCT st.id) AS students,
                   COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) AS present, COUNT(ar.student_id) AS total
            FROM sections sec JOIN classes c ON c.id = sec.class_id LEFT JOIN students st ON st.section_id = sec.id
            LEFT JOIN attendance_records ar ON ar.student_id = st.id AND ar.session_id IN ({_ended_ids_sql()})
            WHERE c.teacher_id = ? GROUP BY sec.id ORDER BY c.name, sec.name""", (teacher_id, teacher_id)).fetchall()
    return [{**dict(r), "percentage": pct(r["present"], r["total"])} for r in rows]


def trend_rows(db, teacher_id, days=30):
    rows = db.execute(
        """SELECT date(s.started_at) AS day, SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present, COUNT(*) AS total
           FROM attendance_records ar JOIN attendance_sessions s ON s.id = ar.session_id
           WHERE s.teacher_id = ? AND s.status = 'ended' GROUP BY day ORDER BY day DESC LIMIT ?""",
        (teacher_id, days)).fetchall()
    return [{"day": r["day"], "percentage": pct(r["present"], r["total"])} for r in reversed(rows)]


def _ids(student_ids):
    return [student_ids] if isinstance(student_ids, int) else list(student_ids)


def student_subject_rows(db, student_ids):
    """Subject-wise attendance for ONE student (sessions without a subject count as 'General').
    Given several ids (a person in several classes) a subject is shown as 'Class - Subject' so DSA Maths and OOPS Maths stay apart."""
    ids = _ids(student_ids)
    if not ids:
        return []
    rows = db.execute(
        f"""SELECT COALESCE(sub.name, 'General') AS subject, COALESCE(csub.name, csec.name) AS class_name,
                  SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present, COUNT(*) AS total
           FROM attendance_records ar JOIN attendance_sessions s ON s.id = ar.session_id AND s.status = 'ended'
           LEFT JOIN subjects sub ON sub.id = s.subject_id LEFT JOIN classes csub ON csub.id = sub.class_id
           LEFT JOIN sections secn ON secn.id = s.section_id LEFT JOIN classes csec ON csec.id = secn.class_id
           WHERE ar.student_id IN ({",".join("?" * len(ids))}) GROUP BY COALESCE(sub.name, 'General'), COALESCE(csub.name, csec.name)
           ORDER BY class_name, subject""", ids).fetchall()
    merged = {}
    for r in rows:
        key = f"{r['class_name']} - {r['subject']}" if len(ids) > 1 and r["class_name"] else r["subject"]
        m = merged.setdefault(key, {"subject": key, "present": 0, "total": 0})
        m["present"] += r["present"]; m["total"] += r["total"]
    return [{**m, "percentage": pct(m["present"], m["total"])} for m in sorted(merged.values(), key=lambda x: x["subject"])]


def student_history_rows(db, student_ids, limit=None, now=None):
    """A student's own records. can_request = absent, no request yet, and still inside the correction window."""
    import time
    from datetime import datetime
    import config
    ids = _ids(student_ids)
    if not ids:
        return []
    now = now or time.time()
    sql = f"""SELECT s.id AS session_id, ar.student_id, s.started_at, s.ended_at, s.label, s.session_type AS type,
                    COALESCE(sub.name, 'General') AS subject, ar.status, rq.status AS request_status
             FROM attendance_records ar JOIN attendance_sessions s ON s.id = ar.session_id AND s.status = 'ended'
             LEFT JOIN subjects sub ON sub.id = s.subject_id
             LEFT JOIN attendance_requests rq ON rq.session_id = s.id AND rq.student_id = ar.student_id
             WHERE ar.student_id IN ({",".join("?" * len(ids))}) ORDER BY s.started_at DESC, s.id DESC"""
    args = list(ids)
    if limit:
        sql += " LIMIT ?"; args.append(limit)
    out = []
    for r in db.execute(sql, args).fetchall():
        d = dict(r)
        ended = datetime.strptime(d["ended_at"], "%Y-%m-%d %H:%M:%S").timestamp() if d["ended_at"] else 0
        d["date"] = (d["started_at"] or "")[:10]
        d["can_request"] = d["status"] == "absent" and d["request_status"] is None and now - ended <= config.REQUEST_WINDOW_DAYS * 86400
        del d["ended_at"], d["student_id"]
        out.append(d)
    return out


def threshold_advice(present, total, threshold):
    """Concrete numbers: how many classes in a row to reach the threshold, or how many can still be missed."""
    return core.advice(present, total, threshold)           # C++: qm::AttendanceStats::advice


def subject_matrix(db, teacher_id):
    """{student_id: {subject name: (present, total)}} over all of the teacher's ended sessions."""
    out = {}
    for r in db.execute(
            """SELECT ar.student_id, COALESCE(sub.name, 'General') AS subject,
                      SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present, COUNT(*) AS total
               FROM attendance_records ar JOIN attendance_sessions s ON s.id = ar.session_id AND s.status = 'ended' AND s.teacher_id = ?
               LEFT JOIN subjects sub ON sub.id = s.subject_id GROUP BY ar.student_id, COALESCE(sub.name, 'General')""", (teacher_id,)).fetchall():
        out.setdefault(r["student_id"], {})[r["subject"]] = (r["present"], r["total"])
    return out
