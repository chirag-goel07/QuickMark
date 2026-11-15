"""Helpers that make sure a teacher only touches their OWN classes, sections and students."""


def own_class(db, teacher_id, class_id):
    return db.execute("SELECT * FROM classes WHERE id = ? AND teacher_id = ?", (class_id, teacher_id)).fetchone()


def own_section(db, teacher_id, section_id):
    return db.execute(
        """SELECT sec.*, c.name AS class_name FROM sections sec
           JOIN classes c ON c.id = sec.class_id
           WHERE sec.id = ? AND c.teacher_id = ?""", (section_id, teacher_id)).fetchone()


def own_subject(db, teacher_id, subject_id):
    return db.execute(
        """SELECT sub.* FROM subjects sub
           JOIN classes c ON c.id = sub.class_id
           WHERE sub.id = ? AND c.teacher_id = ?""", (subject_id, teacher_id)).fetchone()


def own_student(db, teacher_id, student_id):
    return db.execute(
        """SELECT st.*, u.email FROM students st
           JOIN users u ON u.id = st.user_id
           JOIN sections sec ON sec.id = st.section_id
           JOIN classes c ON c.id = sec.class_id
           WHERE st.id = ? AND c.teacher_id = ?""", (student_id, teacher_id)).fetchone()


def clean_name(value, label, max_len=60):
    """Returns (cleaned_text, error_message)."""
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        return None, f"{label} is required."
    if len(text) > max_len:
        return None, f"{label} must be at most {max_len} characters."
    return text, None
