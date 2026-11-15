"""Low-attendance alerts.

* When a session ends, every student who is now below their teacher's threshold gets an IN-APP notification
  (once a week at most). If the teacher turned on 'email students' and SMTP is set up, they get an email too.
* Once a week the teacher can get a summary email of everyone below the threshold.
"""
import logging
import time

from services import emails, people
from services.attendance_stats import student_overall

log = logging.getLogger("quickmark.alerts")
COOLDOWN_SECONDS = 7 * 86400


def after_session(db, session_id, now=None):
    now = time.time() if now is None else now
    rows = db.execute(
        """SELECT st.id AS student_id, st.user_id, st.name, u.email, t.warning_threshold, t.name AS teacher_name, t.auto_alerts,
                  c.name AS class_name, sec.name AS section_name
           FROM attendance_records ar JOIN students st ON st.id = ar.student_id JOIN users u ON u.id = st.user_id
           JOIN sections sec ON sec.id = st.section_id JOIN classes c ON c.id = sec.class_id JOIN teachers t ON t.id = c.teacher_id
           WHERE ar.session_id = ?""", (session_id,)).fetchall()
    sent = 0
    for r in rows:
        pct, _present, total = student_overall(db, r["student_id"])
        if pct is None or not total:
            continue
        if pct >= r["warning_threshold"]:
            db.execute("DELETE FROM alert_log WHERE student_id = ?", (r["student_id"],))     # recovered: warn again if they drop later
            continue
        last = db.execute("SELECT last_alert_at FROM alert_log WHERE student_id = ?", (r["student_id"],)).fetchone()
        if last and now - last["last_alert_at"] < COOLDOWN_SECONDS:
            continue
        where = f"{r['class_name']} - {r['section_name']}"
        people.notify(db, r["user_id"], "low_attendance",
                      f"Your attendance in {where} is {pct:g}%, below the required {r['warning_threshold']}%. Please attend your next classes.")
        db.execute("INSERT INTO alert_log (student_id, last_alert_at) VALUES (?, ?) ON CONFLICT(student_id) DO UPDATE SET last_alert_at = excluded.last_alert_at",
                   (r["student_id"], now))
        sent += 1
        if r["auto_alerts"] and emails.smtp_configured():
            subject, body = emails.warning_message(r["teacher_name"], r["name"], pct, r["warning_threshold"])
            emails.send_in_background(r["email"], subject, body)
    db.commit()
    return sent


def safe_after_session(db, session_id, now=None):
    """Never lets an alert problem break ending a session."""
    try:
        return after_session(db, session_id, now)
    except Exception:
        log.exception("alerts failed")
        try:
            db.rollback()
        except Exception:
            pass
        return 0


# ---------------------------------------------------------------- weekly summary for the teacher
def _summary_text(db, teacher):
    from services.attendance_stats import low_attendance_students
    low = low_attendance_students(db, teacher["id"], teacher["warning_threshold"])
    sessions = db.execute("SELECT COUNT(*) FROM attendance_sessions WHERE teacher_id = ? AND status = 'ended' AND started_at >= datetime('now', '-7 days')",
                          (teacher["id"],)).fetchone()[0]
    lines = [f"Hello {teacher['name']},", "", f"Weekly QuickMark summary: {sessions} session(s) in the last 7 days.", ""]
    if not low:
        lines.append(f"Nobody is below {teacher['warning_threshold']}% right now. 🎉")
    else:
        lines.append(f"{len(low)} student(s) below {teacher['warning_threshold']}%:")
        for s in low[:100]:
            lines.append(f"  - {s['name']} ({s['roll_no']}), {s['class_name']} - {s['section_name']}: {s['percentage']:g}%")
        if len(low) > 100:
            lines.append(f"  ... and {len(low) - 100} more (see Reports).")
    lines += ["", "QuickMark"]
    return "QuickMark weekly attendance summary", "\n".join(lines)


def send_summary(db, teacher_id):
    """Emails one teacher their summary now. Returns False if email is not set up."""
    if not emails.smtp_configured():
        return False
    t = db.execute("SELECT t.*, u.email FROM teachers t JOIN users u ON u.id = t.user_id WHERE t.id = ?", (teacher_id,)).fetchone()
    subject, body = _summary_text(db, t)
    emails.send_in_background(t["email"], subject, body)
    db.execute("UPDATE teachers SET last_summary_at = datetime('now') WHERE id = ?", (teacher_id,))
    db.commit()
    return True


def weekly_tick(db):
    """Called about once an hour by the background loop: sends the summary to teachers who are due."""
    if not emails.smtp_configured():
        return 0
    due = db.execute("SELECT id FROM teachers WHERE weekly_summary = 1 AND (last_summary_at IS NULL OR last_summary_at <= datetime('now', '-7 days'))").fetchall()
    return sum(1 for r in due if send_summary(db, r["id"]))


def maintenance_loop(db_path, sleep):
    from database.db import _connect
    while True:
        try:
            conn = _connect(db_path)
            try:
                weekly_tick(conn)
            finally:
                conn.close()
        except Exception:
            log.exception("weekly summary error")
        sleep(3600)
