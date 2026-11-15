// Classes page: classes, sections and subjects (all stored in the database through the API).
let content, classes = [];

async function load() {
    try { classes = (await api('/api/teacher/classes')).classes; render(); }
    catch (e) { handleApiError(e); content.innerHTML = '<div class="loading">Could not load classes.</div>'; }
}

function render() {
    const cards = classes.map(c => `
      <div class="card class-card" data-id="${c.id}">
        <div class="head">
          <h3>🎓 ${esc(c.name)}</h3><span class="count">${c.student_count} student${c.student_count === 1 ? '' : 's'}</span>
          <div class="grow"></div>
          <a class="btn-ghost btn-sm" style="text-decoration:none" href="/teacher/students.html?class_id=${c.id}">View Students</a>
          <button class="btn-ghost btn-sm" data-act="edit-class">Edit</button>
          <button class="btn-danger btn-sm" data-act="del-class">Delete</button>
        </div>
        <div class="chips-label">Sections</div>
        <div class="chips">
          ${c.sections.map(s => `<span class="chip" data-sid="${s.id}">
              <a href="/teacher/students.html?class_id=${c.id}&section_id=${s.id}" title="View students">${esc(s.name)} · ${s.student_count}</a>
              <button class="x" data-act="join" title="Join code for students">${s.join_mode === 'off' ? '🔗' : '🟢'}</button>
              <button class="x" data-act="edit-section" title="Rename">✎</button>
              <button class="x" data-act="del-section" title="Delete">✕</button></span>`).join('')}
          <button class="chip-add" data-act="add-section">+ Section</button>
        </div>
        <div class="chips-label">Subjects</div>
        <div class="chips">
          ${c.subjects.map(s => `<span class="chip subject" data-sub="${s.id}">${esc(s.name)}
              <button class="x" data-act="edit-subject" title="Rename">✎</button>
              <button class="x" data-act="del-subject" title="Delete">✕</button></span>`).join('')}
          <button class="chip-add" data-act="add-subject">+ Subject</button>
        </div>
      </div>`).join('');

    content.innerHTML = `
      <div class="toolbar"><div class="grow"></div><button class="btn-primary" id="addClass">+ Add Class</button></div>
      ${cards || '<div class="card"><div class="empty">No classes yet. Click “Add Class” to create your first one (for example “CSE - 2nd Sem”).</div></div>'}`;
}

function nameForm(title, label, value, onSave) {
    formDialog(title, [{ name: 'name', label, value, required: true }], async v => { await onSave(v.name); await load(); });
}

function joinDialog(cls, sec) {
    const fmt = c => c ? c.slice(0, 4) + '-' + c.slice(4) : '';
    const o = _openModal('<div id="jBody"></div>');
    o.querySelector('.modal').classList.add('wide');
    const draw = () => {
        const link = sec.join_code ? `${location.origin}/student/join.html?code=${sec.join_code}` : '';
        o.querySelector('#jBody').innerHTML = `<h3>Join code - ${esc(cls.name)} / ${esc(sec.name)}</h3>
          <div class="subtle" style="margin-bottom:10px">Students type this code (or open the link) to add themselves, so you do not have to enter them one by one.</div>
          <div class="error-msg" id="jErr"></div>
          ${['off', 'open', 'approval'].map(m => `<label class="check" style="display:block;margin:6px 0"><input type="radio" name="jm" value="${m}" ${sec.join_mode === m ? 'checked' : ''}>
              <b>${{ off: 'Off', open: 'Open', approval: 'Needs my approval' }[m]}</b> <span class="subtle">- ${{ off: 'nobody can join with a code', open: 'students join at once (best when you share the code only in your class)', approval: 'you accept or reject each student on the Students page' }[m]}</span></label>`).join('')}
          ${sec.join_code ? `<div style="text-align:center;margin:14px 0"><div style="font-size:30px;font-weight:700;letter-spacing:4px">${fmt(sec.join_code)}</div>
              <div class="subtle" style="word-break:break-all">${esc(link)}</div></div>` : ''}
          <div class="foot">${sec.join_code ? '<button class="btn-ghost" id="jNew">New code</button><button class="btn-ghost" id="jCopy">Copy link</button>' : ''}<button class="btn-primary" id="jClose">Done</button></div>`;
        o.querySelectorAll('input[name=jm]').forEach(r => r.onchange = () => put({ mode: r.value }));
        const nb = o.querySelector('#jNew'); if (nb) nb.onclick = async () => { if (await confirmDialog('Make a new code? The old code stops working immediately.', 'New code')) put({ regenerate: true }); };
        const cb = o.querySelector('#jCopy'); if (cb) cb.onclick = () => { navigator.clipboard.writeText(link).then(() => toast('Link copied.', 'success'), () => toast('Copy it by hand.', 'error')); };
        o.querySelector('#jClose').onclick = () => { o.remove(); load(); };
    };
    const put = async body => {
        try { const r = await api(`/api/teacher/join/sections/${sec.id}`, { method: 'PUT', body }); sec.join_mode = r.join_mode; sec.join_code = r.join_code ? r.join_code.replace('-', '') : null; draw(); }
        catch (e) { const er = o.querySelector('#jErr'); er.textContent = e.message; er.classList.add('show'); }
    };
    draw();
}

async function removeItem(url, message, okText) {
    if (!await confirmDialog(message, okText)) return;
    try { await api(url, { method: 'DELETE' }); toast('Deleted.', 'success'); await load(); }
    catch (e) { handleApiError(e); }
}

async function init() {
    content = await initPage('classes', 'Classes', 'Manage classes, sections and subjects');
    if (!content) return;
    content.addEventListener('click', e => {
        if (e.target.id === 'addClass') {
            return nameForm('Add Class', 'Class name', '', async n => { await api('/api/teacher/classes', { method: 'POST', body: { name: n } }); toast('Class added.', 'success'); });
        }
        const btn = e.target.closest('[data-act]'); if (!btn) return;
        const card = btn.closest('.class-card'), cls = classes.find(c => String(c.id) === card.dataset.id);
        const sec = btn.closest('[data-sid]') && cls.sections.find(s => String(s.id) === btn.closest('[data-sid]').dataset.sid);
        const sub = btn.closest('[data-sub]') && cls.subjects.find(s => String(s.id) === btn.closest('[data-sub]').dataset.sub);
        switch (btn.dataset.act) {
            case 'edit-class': return nameForm('Edit Class', 'Class name', cls.name, async n => { await api(`/api/teacher/classes/${cls.id}`, { method: 'PUT', body: { name: n } }); toast('Class updated.', 'success'); });
            case 'del-class': return removeItem(`/api/teacher/classes/${cls.id}`, `Delete class “${cls.name}” with all its sections and subjects?\nThis cannot be undone.`);
            case 'add-section': return nameForm('Add Section', 'Section name (e.g. A)', '', async n => { await api(`/api/teacher/classes/${cls.id}/sections`, { method: 'POST', body: { name: n } }); toast('Section added.', 'success'); });
            case 'join': return joinDialog(cls, sec);
            case 'edit-section': return nameForm('Rename Section', 'Section name', sec.name, async n => { await api(`/api/teacher/sections/${sec.id}`, { method: 'PUT', body: { name: n } }); toast('Section updated.', 'success'); });
            case 'del-section': return removeItem(`/api/teacher/sections/${sec.id}`, `Delete section “${sec.name}” from ${cls.name}?`);
            case 'add-subject': return nameForm('Add Subject', 'Subject name', '', async n => { await api(`/api/teacher/classes/${cls.id}/subjects`, { method: 'POST', body: { name: n } }); toast('Subject added.', 'success'); });
            case 'edit-subject': return nameForm('Rename Subject', 'Subject name', sub.name, async n => { await api(`/api/teacher/subjects/${sub.id}`, { method: 'PUT', body: { name: n } }); toast('Subject updated.', 'success'); });
            case 'del-subject': return removeItem(`/api/teacher/subjects/${sub.id}`, `Delete subject “${sub.name}”?`);
        }
    });
    load();
}
init();
