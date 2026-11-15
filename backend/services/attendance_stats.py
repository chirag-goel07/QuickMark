"""Attendance percentages are always calculated on the server from attendance_records.
The percentage maths and the sorting are C++ (cpp/stats.hpp, class qm::AttendanceStats); this file only fetches the rows."""
from services import core

# A student's attendance % = present records / all records from ended sessions.
_PERCENT_SQL = """
SELECT st.id AS student_id, st.roll_no, st.name, u.email,
       c.name AS class_name, sec.name AS section_name,
       SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present,
       COUNT(ar.student_id) AS total
FROM students st
JOIN users u        ON u.id = st.user_id
JOIN sections sec   ON sec.id = st.section_id
JOIN classes c      ON c.id = sec.class_id
JOIN attendance_records ar ON ar.student_id = st.id
JOIN attendance_sessions s ON s.id = ar.session_id AND s.status = 'ended'
WHERE c.teacher_id = ?
GROUP BY st.id
"""


def student_percentages(db, teacher_id):
    out = []
    for r in db.execute(_PERCENT_SQL, (teacher_id,)).fetchall():
        pct = core.percent(r["present"], r["total"]) or 0.0
        out.append({**dict(r), "percentage": pct})
    return out


def overall_percentage(db, teacher_id):
    row = db.execute(
        """SELECT SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present, COUNT(*) AS total
           FROM attendance_records ar
           JOIN attendance_sessions s ON s.id = ar.session_id
           WHERE s.teacher_id = ? AND s.status = 'ended'""", (teacher_id,)).fetchone()
    if not row["total"]:
        return None
    return core.percent(row["present"], row["total"])


def low_attendance_students(db, teacher_id, threshold):
    low = [s for s in student_percentages(db, teacher_id) if s["percentage"] < threshold]
    low = core.sorted_by_value(low, key=lambda s: s["percentage"])
    return [{"student_id": s["student_id"], "name": s["name"], "roll_no": s["roll_no"], "email": s["email"],
             "class_name": s["class_name"], "section_name": s["section_name"],
             "percentage": s["percentage"]} for s in low]


def _id_list(student_ids):
    return [student_ids] if isinstance(student_ids, int) else list(student_ids)


def student_overall(db, student_ids):
    """(percentage or None, present, total) for ONE student (one id) or one person in all their classes (a list of ids)."""
    ids = _id_list(student_ids)
    if not ids:
        return None, 0, 0
    row = db.execute(
        f"""SELECT SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present, COUNT(*) AS total
            FROM attendance_records ar JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE ar.student_id IN ({",".join("?" * len(ids))}) AND s.status = 'ended'""", ids).fetchone()
    total = row["total"] or 0
    present = row["present"] or 0
    return core.percent(present, total), present, total
