// The class the student is enrolled in: section, teacher, every subject with the student's attendance, and groups.
async function init() {
    const content = await initStudent({ active: 'classes' }); if (!content) return;
    let d; try { d = await api('/api/student/classes'); } catch (e) { return onAuthError(e); }
    content.innerHTML = d.classes.map(c => `
      <div class="card class-card"><h3>🎓 ${esc(c.class_name)}</h3>
        <div class="kv" style="margin-top:8px"><div>Section</div><div>${esc(c.section_name)}</div><div>Teacher</div><div>${esc(c.teacher_name)}</div>
          <div>Classmates</div><div>${c.students_in_class} students in this class</div></div></div>
      <div class="card"><h3>Subjects &amp; my attendance</h3>${c.subjects.length ? subjectCard(c.subjects, d.threshold) : '<div class="empty">Your teacher has not added subjects yet.</div>'}</div>
      <div class="card"><h3>My groups</h3>${c.groups.length ? c.groups.map(g => `<span class="chip-s">👥 ${esc(g.name)} · ${g.member_count} students</span>`).join('') : '<div class="empty">You are not in any group. Your teacher may add you for lab or project attendance.</div>'}</div>`).join('');
}
init();
