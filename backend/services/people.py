"""One PERSON can be enrolled in several classes.

users            = the login (one email, one password)
students (rows)  = enrollments: one row per class/section the person is in (roll number and name belong to the enrollment)

Things that belong to the person (face template, profile picture, phone) are kept identical on all their enrollment rows,
so the student enrolls their face / picks a picture only once.
"""
import secrets

from werkzeug.security import generate_password_hash

_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # no 0/O/1/l/I: easy to read out loud


def random_password(n=8):
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def hash_new_password(password):
    return generate_password_hash(password)


def enrollment_ids(db, user_id):
    return [r["id"] for r in db.execute("SELECT id FROM students WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def teachers_of_user(db, user_id):
    """Ids of every teacher who has this person in one of their classes."""
    rows = db.execute(
        """SELECT DISTINCT c.teacher_id FROM students st JOIN sections sec ON sec.id = st.section_id
           JOIN classes c ON c.id = sec.class_id WHERE st.user_id = ?""", (user_id,)).fetchall()
    return {r["teacher_id"] for r in rows}


def copy_person_data(db, user_id, new_student_id):
    """A new enrollment gets the person's existing face template, picture and phone."""
    src = db.execute(
        """SELECT face_descriptor, face_enrolled_at, avatar, avatar_updated_at, phone FROM students
           WHERE user_id = ? AND id != ? ORDER BY (face_descriptor IS NULL), (avatar IS NULL), id LIMIT 1""",
        (user_id, new_student_id)).fetchone()
    if src:
        db.execute("""UPDATE students SET face_descriptor = ?, face_enrolled_at = ?, avatar = ?, avatar_updated_at = ?, phone = COALESCE(phone, ?)
                      WHERE id = ?""",
                   (src["face_descriptor"], src["face_enrolled_at"], src["avatar"], src["avatar_updated_at"], src["phone"], new_student_id))


def user_id_of(db, student_id):
    row = db.execute("SELECT user_id FROM students WHERE id = ?", (student_id,)).fetchone()
    return row["user_id"] if row else None


def set_person_columns(db, student_id, **cols):
    """Update person-level columns (face_descriptor, avatar, phone ...) on ALL enrollments of that person."""
    uid = user_id_of(db, student_id)
    if uid is None:
        return
    names = list(cols)
    db.execute(f"UPDATE students SET {', '.join(n + ' = ?' for n in names)} WHERE user_id = ?", [cols[n] for n in names] + [uid])


# ---------------------------------------------------------------- joining a section with its code
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # no 0/O/1/I


def new_join_code(db):
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if not db.execute("SELECT 1 FROM sections WHERE join_code = ?", (code,)).fetchone():
            return code


def normalize_code(raw):
    return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())


def format_code(code):
    return f"{code[:4]}-{code[4:]}" if code else None


def section_by_code(db, raw):
    """The section a code opens, or None (unknown code, or joining switched off)."""
    code = normalize_code(raw)
    if len(code) != 8:
        return None
    return db.execute(
        """SELECT sec.id, sec.name AS section_name, sec.join_mode, c.name AS class_name, t.name AS teacher_name
           FROM sections sec JOIN classes c ON c.id = sec.class_id JOIN teachers t ON t.id = c.teacher_id
           WHERE sec.join_code = ? AND sec.join_mode IN ('open', 'approval')""", (code,)).fetchone()


def add_enrollment(db, user_id, section_id, roll_no, name, phone, where):
    """Puts an existing login into a section. Returns (student_id, error)."""
    if db.execute("SELECT 1 FROM students WHERE section_id = ? AND roll_no = ?", (section_id, roll_no)).fetchone():
        return None, f"Roll number {roll_no} is already taken in {where}."
    if db.execute("SELECT 1 FROM students WHERE section_id = ? AND user_id = ?", (section_id, user_id)).fetchone():
        return None, f"You are already in {where}."
    sid = db.execute("INSERT INTO students (user_id, roll_no, name, phone, section_id) VALUES (?, ?, ?, ?, ?)",
                     (user_id, roll_no, name, phone, section_id)).lastrowid
    copy_person_data(db, user_id, sid)
    return sid, None


def notify(db, user_id, kind, message):
    db.execute("INSERT INTO notifications (user_id, kind, message) VALUES (?, ?, ?)", (user_id, kind, message[:300]))
