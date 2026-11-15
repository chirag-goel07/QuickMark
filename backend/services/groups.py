"""Groups made of sections: keeps group_members equal to "every student currently in the group's sections"."""

_IN_SECTIONS = "SELECT id FROM students WHERE section_id IN (SELECT section_id FROM group_sections WHERE group_id = ?)"


def is_section_group(db, group_id):
    return db.execute("SELECT 1 FROM group_sections WHERE group_id = ?", (group_id,)).fetchone() is not None


def sync_members(db, group_id):
    """Section groups: members = students in the ticked sections right now (new students are added, removed ones dropped).
    Groups that were made by picking single students (no sections stored) are left alone. Does not commit."""
    if not is_section_group(db, group_id):
        return
    db.execute(f"DELETE FROM group_members WHERE group_id = ? AND student_id NOT IN ({_IN_SECTIONS})", (group_id, group_id))
    db.execute(f"INSERT OR IGNORE INTO group_members (group_id, student_id) {_IN_SECTIONS.replace('SELECT id', 'SELECT ?, id', 1)}", (group_id, group_id))


def sections_of(db, group_id):
    """The group's sections with the number of its students in each. Legacy groups: the sections their students belong to."""
    if is_section_group(db, group_id):
        rows = db.execute(
            """SELECT sec.id, sec.name, c.name AS class_name, COUNT(st.id) AS student_count
               FROM group_sections gs JOIN sections sec ON sec.id = gs.section_id JOIN classes c ON c.id = sec.class_id
               LEFT JOIN students st ON st.section_id = sec.id WHERE gs.group_id = ? GROUP BY sec.id ORDER BY c.name, sec.name""", (group_id,)).fetchall()
    else:
        rows = db.execute(
            """SELECT sec.id, sec.name, c.name AS class_name, COUNT(st.id) AS student_count
               FROM group_members gm JOIN students st ON st.id = gm.student_id JOIN sections sec ON sec.id = st.section_id
               JOIN classes c ON c.id = sec.class_id WHERE gm.group_id = ? GROUP BY sec.id ORDER BY c.name, sec.name""", (group_id,)).fetchall()
    return [dict(r) for r in rows]
