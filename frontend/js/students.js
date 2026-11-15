// Students page: list, search, filter by class/section, add, edit, delete.
let content, classes = [], students = [], threshold = 75;
const params = new URLSearchParams(location.search);
const filters = { search: '', class_id: params.get('class_id') || '', section_id: params.get('section_id') || '', low: params.get('low') === '1' };

function sectionOptions(classId, withAll) {
    const c = classes.find(x => String(x.id) === String(classId));
    const opts = c ? c.sections.map(s => ({ value: s.id, label: s.name })) : [];
    return withAll ? [{ value: '', label: 'All sections' }, ...opts] : opts;
}

function renderShell() {
    const classOpts = ['<option value="">All classes</option>'].concat(
        classes.map(c => `<option value="${c.id}"${String(c.id) === filters.class_id ? ' selected' : ''}>${esc(c.name)}</option>`)).join('');
    content.innerHTML = `
      <div class="card"><div class="toolbar">
        <div class="field grow"><label>Search</label><input type="text" id="search" placeholder="Name, roll number or email" value="${esc(filters.search)}"></div>
        <div class="field"><label>Class</label><select id="fClass">${classOpts}</select></div>
        <div class="field"><label>Section</label><select id="fSec"></select></div>
        <label class="check"><input type="checkbox" id="fLow"${filters.low ? ' checked' : ''}> Low attendance only</label>
        <button class="btn-ghost" id="joinReq">📥 Join requests<span id="joinCount"></span></button>
        <button class="btn-ghost" id="emailLow">✉ Email All Low-Attendance</button>
        <button class="btn-ghost" id="bulkAdd">⬆ Import many (CSV / paste)</button>
        <button class="btn-primary" id="addStudent">+ Add Student</button>
      </div></div>
      <div class="card"><div class="table-wrap" id="tableBox"><div class="loading">Loading students...</div></div></div>`;
    fillSectionFilter();
}

function fillSectionFilter() {
    const sel = document.getElementById('fSec');
    sel.innerHTML = sectionOptions(filters.class_id, true).map(o => `<option value="${o.value}"${String(o.value) === filters.section_id ? ' selected' : ''}>${esc(o.label)}</option>`).join('');
    sel.disabled = !filters.class_id;
}

async function loadStudents() {
    const q = new URLSearchParams();
    if (filters.search) q.set('search', filters.search);
    if (filters.class_id) q.set('class_id', filters.class_id);
    if (filters.section_id) q.set('section_id', filters.section_id);
    if (filters.low) q.set('low', '1');
    try {
        const d = await api('/api/teacher/students?' + q); students = d.students; threshold = d.threshold;
        renderTable();
    } catch (e) { handleApiError(e); }
}

// A header line before each section's students ("ML - ML1 · 4 students"), so the list reads section by section.
function sectionHeaderRow(s) {
    const n = students.filter(x => x.section_id === s.section_id).length;
    return `<tr class="sec-row"><td colspan="9"><b>${esc(s.class_name)} - ${esc(s.section_name)}</b> <span class="subtle">· ${n} student${n === 1 ? '' : 's'}</span></td></tr>`;
}

// Click a student's name: profile, class attendance, subject-wise attendance and recent sessions.
async function showStudent(id) {
    let d;
    try { d = await api('/api/teacher/students/' + id + '/details'); } catch (e) { return toast(e.message, 'error'); }
    const s = d.student, o = d.overall, adv = o.advice;
    const advice = !adv ? '' : adv.status === 'ok' ? `Can still miss ${adv.can_miss} class${adv.can_miss === 1 ? '' : 'es'} and stay at ${o.threshold}% or above.`
        : adv.classes_needed ? `Must attend the next ${adv.classes_needed} classes in a row to reach ${o.threshold}%.` : `Cannot reach ${o.threshold}% any more.`;
    const pill = p => p === null ? '<span class="pill none">--</span>' : `<span class="pill ${p < o.threshold ? '' : 'ok'}">${p}%</span>`;
    const ov = _openModal(`<div class="detail-head">${stuAvatar(s.id, s.name, s.has_avatar, s.avatar_v, 56)}
        <div><h3>${esc(s.name)}</h3><span class="subtle">Roll no ${esc(s.roll_no)}</span></div></div>
      <div class="detail-grid">
        <div><b>Class / Section</b>${esc(s.class_name)} - ${esc(s.section_name)}</div><div><b>Face check</b>${s.face_enrolled ? 'Enrolled' : 'Not set up'}</div>
        <div><b>Email</b>${esc(s.email)}</div><div><b>Phone</b>${esc(s.phone || '-')}</div></div>
      <div class="chips-label">Class attendance</div>
      ${o.total ? `<div class="progress${o.is_low ? '' : ' green'}"><div style="width:${o.percentage}%"></div></div>
        <div class="detail-stats"><div><b>${o.percentage}%</b>overall</div><div><b>${o.present}</b>present</div><div><b>${o.absent}</b>absent</div><div><b>${o.total}</b>sessions</div></div>
        <div class="subtle" style="margin-top:6px">${o.is_low ? `⚠ Below the ${o.threshold}% warning line. ` : ''}${esc(advice)}</div>`
        : '<div class="empty" style="padding:10px">No attendance recorded yet.</div>'}
      ${d.subjects.length ? `<div class="chips-label">Subject-wise</div><div class="table-wrap"><table class="data"><thead><tr><th>Subject</th><th>Present</th><th>Total</th><th>%</th></tr></thead><tbody>${
        d.subjects.map(x => `<tr><td>${esc(x.subject)}</td><td>${x.present}</td><td>${x.total}</td><td>${pill(x.percentage)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${d.history.length ? `<div class="chips-label">Recent sessions</div><div class="table-wrap"><table class="data"><thead><tr><th>Date</th><th>Class / Group</th><th>Subject</th><th>Status</th></tr></thead><tbody>${
        d.history.map(h => `<tr><td>${esc(h.date)}</td><td>${esc(h.label)}</td><td>${esc(h.subject)}</td><td><span class="pill ${h.status === 'present' ? 'ok' : ''}">${h.status === 'present' ? 'Present' : 'Absent'}</span></td></tr>`).join('')}</tbody></table></div>` : ''}
      <div class="foot"><button class="btn-primary" id="dClose">Close</button></div>`);
    ov.querySelector('.modal').classList.add('xwide');
    ov.querySelector('#dClose').onclick = () => ov.remove();
}

function renderTable() {
    const box = document.getElementById('tableBox');
    if (!students.length) {
        box.innerHTML = `<div class="empty">${classes.length ? 'No students match.' : 'Create a class and section first (Classes page), then add students.'}</div>`;
        return;
    }
    box.innerHTML = `<table class="data"><thead><tr><th>Roll No</th><th>Name</th><th>Email</th><th>Phone</th><th>Class</th><th>Section</th><th>Face</th><th>Attendance</th><th></th></tr></thead><tbody>` +
        students.map((s, i) => `${(i === 0 || students[i - 1].section_id !== s.section_id) ? sectionHeaderRow(s) : ''}<tr data-id="${s.id}">
            <td>${esc(s.roll_no)}</td><td><div style="display:flex;align-items:center;gap:8px">${stuAvatar(s.id, s.name, s.has_avatar, s.avatar_v, 30)}<button type="button" class="stu-link" data-act="details">${esc(s.name)}</button></div></td><td>${esc(s.email)}</td><td>${esc(s.phone || '-')}</td>
            <td>${esc(s.class_name)}</td><td>${esc(s.section_name)}</td>
            <td>${s.face_enrolled ? '<span class="pill ok">Enrolled</span>' : '<span class="pill none">Not set</span>'}</td>
            <td>${s.percentage === null ? '<span class="pill none">--</span>' : `<span class="pill ${s.is_low ? '' : 'ok'}">${s.percentage}%</span>`}</td>
            <td class="actions">${s.is_low ? '<button class="btn-ghost btn-sm" data-act="email">✉ Email Warning</button>' : ''}${s.face_enrolled ? '<button class="btn-ghost btn-sm" data-act="resetface">Reset face</button>' : ''}<button class="btn-ghost btn-sm" data-act="resetpw">Reset password</button><button class="btn-ghost btn-sm" data-act="edit">Edit</button><button class="btn-danger btn-sm" data-act="del">Delete</button></td></tr>`).join('') +
        `</tbody></table><div class="subtle" style="margin-top:10px">${students.length} student${students.length === 1 ? '' : 's'} · warning threshold ${threshold}%</div>`;
}

function studentForm(st) {
    if (!classes.some(c => c.sections.length)) { toast('Add a class with at least one section first.', 'error'); return; }
    const isEdit = !!st;
    const startClass = isEdit ? st.class_id : (filters.class_id && classes.find(c => String(c.id) === filters.class_id && c.sections.length) ? filters.class_id : classes.find(c => c.sections.length).id);
    const o = formDialog(isEdit ? 'Edit Student' : 'Add Student', [
        { name: 'roll_no', label: 'Roll number', value: isEdit ? st.roll_no : '', required: true },
        { name: 'name', label: 'Full name', value: isEdit ? st.name : '', required: true },
        { name: 'email', label: 'Email', type: 'email', value: isEdit ? st.email : '', required: true, hint: isEdit ? 'The student logs in with this email.' : 'The student logs in with this email. If they are already in another class, they are simply added to this one too.' },
        { name: 'phone', label: 'Phone (optional)', value: isEdit ? st.phone : '' },
        { name: 'class_id', label: 'Class', value: startClass, required: true, options: classes.filter(c => c.sections.length).map(c => ({ value: c.id, label: c.name })) },
        { name: 'section_id', label: 'Section', value: isEdit ? st.section_id : '', required: true, options: sectionOptions(startClass, false) },
        { name: 'password', label: isEdit ? 'New password (leave blank to keep current)' : 'First password (leave blank to generate one)', type: 'password', required: false, hint: 'At least 6 characters. The student can change it after logging in (Profile -> Change password).' },
    ], async v => {
        const body = { roll_no: v.roll_no, name: v.name, email: v.email, phone: v.phone, section_id: v.section_id, password: v.password };
        let res = null;
        if (!isEdit) res = await api('/api/teacher/students', { method: 'POST', body });
        else await api(`/api/teacher/students/${st.id}`, { method: 'PUT', body });
        toast(isEdit ? 'Student updated.' : (res.status === 'enrolled' ? 'Student already had a login - added to this class.' : 'Student added.'), 'success');
        await refreshAll();
        if (res && res.generated_password) showCredentials([{ roll_no: v.roll_no, name: v.name, email: v.email, password: res.generated_password }]);
    });
    // when the class changes, reload the section choices
    o.querySelector('[name=class_id]').addEventListener('change', e => {
        o.querySelector('[name=section_id]').innerHTML = sectionOptions(e.target.value, false).map(x => `<option value="${x.value}">${esc(x.label)}</option>`).join('');
    });
}

// ---------------------------------------------------------------- join requests (students who used a class code)
async function updateJoinCount() {
    try { const r = await api('/api/teacher/join/requests'); const el = document.getElementById('joinCount'); if (el) el.textContent = r.count ? ` (${r.count})` : ''; } catch (e) { /* ignore */ }
}
async function joinRequestsDialog() {
    let r; try { r = await api('/api/teacher/join/requests'); } catch (e) { return handleApiError(e); }
    const o = _openModal('<div id="jrBody"></div>'); o.querySelector('.modal').classList.add('wide');
    const draw = () => {
        o.querySelector('#jrBody').innerHTML = `<h3>Join requests</h3>` + (r.requests.length ? `<div class="table-wrap" style="max-height:55vh;overflow:auto"><table class="data"><thead><tr><th>Name</th><th>Roll</th><th>Email</th><th>Wants to join</th><th></th></tr></thead><tbody>
            ${r.requests.map(x => `<tr data-id="${x.id}"><td>${esc(x.name)}</td><td>${esc(x.roll_no)}</td><td>${esc(x.email)}${x.existing_login ? ' <span class="subtle">(has a login)</span>' : ''}</td><td>${esc(x.class_name)} - ${esc(x.section_name)}</td>
            <td class="actions"><button class="btn-primary btn-sm" data-do="approve">Accept</button><button class="btn-danger btn-sm" data-do="reject">Reject</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No requests waiting.</div>')
            + '<div class="foot"><button class="btn-primary" id="jrClose">Close</button></div>';
        o.querySelector('#jrClose').onclick = () => { o.remove(); refreshAll(); };
        o.querySelectorAll('[data-do]').forEach(b => b.onclick = async () => {
            const id = b.closest('tr').dataset.id; b.disabled = true;
            try { await api(`/api/teacher/join/requests/${id}/${b.dataset.do}`, { method: 'POST' }); r.requests = r.requests.filter(x => String(x.id) !== id); r.count = r.requests.length; draw(); toast(b.dataset.do === 'approve' ? 'Student added.' : 'Request rejected.', 'success'); }
            catch (err) { toast(err.message, 'error'); b.disabled = false; }
        });
    };
    draw();
}

// ---------------------------------------------------------------- bulk import
function parseTable(text) {
    text = text.replace(/^\uFEFF/, '');
    const first = text.split(/\r?\n/).find(l => l.trim()) || '';
    const delim = first.includes('\t') ? '\t' : (first.split(';').length > first.split(',').length ? ';' : ',');
    const rows = []; let row = [], cell = '', q = false;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; }
        else if (ch === '"') q = true;
        else if (ch === delim) { row.push(cell); cell = ''; }
        else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); cell = ''; if (row.some(c => c.trim())) rows.push(row); row = []; }
        else cell += ch;
    }
    row.push(cell); if (row.some(c => c.trim())) rows.push(row);
    return rows.map(r => r.map(c => c.trim()));
}
function tableToStudents(rows) {
    if (!rows.length) return [];
    const norm = h => h.toLowerCase().replace(/[^a-z]/g, '');
    const alias = { roll_no: ['rollno', 'roll', 'rollnumber', 'regno', 'id'], name: ['name', 'studentname', 'fullname'], email: ['email', 'emailid', 'mail'], phone: ['phone', 'mobile', 'phoneno', 'contact'], password: ['password', 'pass'] };
    const head = rows[0].map(norm);
    const hasHeader = head.includes('email') || head.includes('emailid') || head.includes('name') || head.includes('rollno');
    const col = {};
    if (hasHeader) Object.keys(alias).forEach(k => { const i = head.findIndex(h => alias[k].includes(h)); if (i >= 0) col[k] = i; });
    else ['roll_no', 'name', 'email', 'phone', 'password'].forEach((k, i) => col[k] = i);
    return (hasHeader ? rows.slice(1) : rows).map(r => Object.fromEntries(Object.keys(col).map(k => [k, r[col[k]] || ''])));
}
function downloadCsv(name, header, rows) {
    const cell = v => { v = String(v == null ? '' : v); if (/^[=+\-@]/.test(v)) v = "'" + v; return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const blob = new Blob(['\uFEFF' + [header, ...rows].map(r => r.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
}
function showCredentials(list, title) {
    const o = _openModal(`<h3>${esc(title || 'Login details to give the student')}</h3>
        <div class="subtle" style="margin-bottom:10px">Passwords are shown <b>only now</b>. Students can log in with this and change it later in Profile.</div>
        <div class="table-wrap" style="max-height:50vh;overflow:auto"><table class="data"><thead><tr><th>Roll</th><th>Name</th><th>Email</th><th>First password</th></tr></thead><tbody>
        ${list.map(c => `<tr><td>${esc(c.roll_no)}</td><td>${esc(c.name)}</td><td>${esc(c.email)}</td><td><code>${esc(c.password)}</code></td></tr>`).join('')}</tbody></table></div>
        <div class="foot"><button class="btn-ghost" id="crCsv">⬇ Download CSV</button><button class="btn-primary" id="crClose">Done</button></div>`);
    o.querySelector('.modal').classList.add('wide');
    o.querySelector('#crCsv').onclick = () => downloadCsv('student_logins.csv', ['Roll No', 'Name', 'Email', 'First password'], list.map(c => [c.roll_no, c.name, c.email, c.password]));
    o.querySelector('#crClose').onclick = () => o.remove();
}
function bulkDialog() {
    const withSec = classes.filter(c => c.sections.length);
    if (!withSec.length) { toast('Add a class with at least one section first.', 'error'); return; }
    const startClass = filters.class_id && withSec.find(c => String(c.id) === filters.class_id) ? filters.class_id : withSec[0].id;
    const o = _openModal(`<h3>Import many students</h3><div class="error-msg" id="bkErr"></div>
        <div class="subtle" style="margin-bottom:10px">Pick the section, then upload a CSV file <i>or</i> copy the rows from Excel / Google Sheets and paste them. Columns: <b>roll_no, name, email</b>, phone (optional), password (optional).</div>
        <div class="row" style="gap:10px"><div class="field" style="flex:1"><label>Class</label><select id="bkClass">${withSec.map(c => `<option value="${c.id}"${String(c.id) === String(startClass) ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select></div>
        <div class="field" style="flex:1"><label>Section</label><select id="bkSec"></select></div></div>
        <div class="row" style="gap:10px;align-items:center;margin:8px 0"><label class="btn-ghost" style="cursor:pointer;padding:8px 14px">📄 Choose CSV file<input type="file" id="bkFile" accept=".csv,.txt,text/csv" hidden></label>
          <a href="/api/teacher/students/template.csv" class="subtle">Download template</a></div>
        <div class="field"><label>…or paste rows here</label><textarea id="bkText" rows="7" style="width:100%;font-family:monospace" placeholder="roll_no,name,email&#10;1,Asha Verma,asha@college.edu&#10;2,Ravi Kumar,ravi@college.edu"></textarea></div>
        <div class="field"><label>Same first password for everyone (optional)</label><input type="text" id="bkPw" placeholder="Leave blank = a different random password for each student" autocomplete="off">
          <div class="hint">Students can change it after logging in. If a student's email already has a QuickMark login (e.g. from another class), they are just added to this class.</div></div>
        <div id="bkPreview" class="subtle"></div>
        <div class="foot"><button class="btn-ghost" id="bkCancel">Cancel</button><button class="btn-primary" id="bkGo">Import</button></div>`);
    o.querySelector('.modal').classList.add('wide');
    const $ = sel => o.querySelector(sel);
    const fillSec = () => { $('#bkSec').innerHTML = sectionOptions($('#bkClass').value, false).map(x => `<option value="${x.value}">${esc(x.label)}</option>`).join(''); };
    fillSec(); $('#bkClass').onchange = fillSec;
    const current = () => tableToStudents(parseTable($('#bkText').value));
    const preview = () => { const n = current().length; $('#bkPreview').textContent = n ? `${n} student${n === 1 ? '' : 's'} ready to import.` : ''; };
    $('#bkText').oninput = preview;
    $('#bkFile').onchange = async e => { const f = e.target.files[0]; if (f) { $('#bkText').value = await f.text(); preview(); } };
    $('#bkCancel').onclick = () => o.remove();
    $('#bkGo').onclick = async () => {
        const err = $('#bkErr'), rows = current(); err.classList.remove('show');
        if (!rows.length) { err.textContent = 'Choose a file or paste some rows first.'; err.classList.add('show'); return; }
        const b = $('#bkGo'); b.disabled = true; b.textContent = 'Importing...';
        try {
            const r = await api('/api/teacher/students/bulk', { method: 'POST', body: { section_id: $('#bkSec').value, default_password: $('#bkPw').value, rows } });
            o.remove(); await refreshAll();
            const bad = r.results.filter(x => x.status === 'error'), made = r.results.filter(x => x.status === 'created');
            toast(`${r.created} added, ${r.enrolled} linked to an existing login, ${r.failed} skipped.`, r.failed ? 'error' : 'success');
            if (bad.length || made.length) showBulkResult(r, made, bad);
        } catch (e) { err.textContent = e.message; err.classList.add('show'); b.disabled = false; b.textContent = 'Import'; }
    };
}
function showBulkResult(r, made, bad) {
    const o = _openModal(`<h3>Import finished - ${esc(r.section)}</h3>
        <div class="subtle" style="margin-bottom:8px">${r.created} new · ${r.enrolled} already had a login · ${r.failed} skipped</div>
        ${bad.length ? `<div class="chips-label">Skipped rows (fix them and import again)</div><div class="table-wrap" style="max-height:28vh;overflow:auto"><table class="data"><tbody>${bad.map(x => `<tr><td>Row ${x.row}</td><td>${esc(x.roll_no)} ${esc(x.name)} ${esc(x.email)}</td><td>${esc(x.message)}</td></tr>`).join('')}</tbody></table></div>` : ''}
        <div class="foot">${made.length ? '<button class="btn-ghost" id="brCred">Show first passwords</button>' : ''}<button class="btn-primary" id="brClose">Done</button></div>`);
    o.querySelector('.modal').classList.add('wide');
    o.querySelector('#brClose').onclick = () => o.remove();
    const c = o.querySelector('#brCred'); if (c) c.onclick = () => { o.remove(); showCredentials(made); };
    if (made.length && !bad.length) { o.remove(); showCredentials(made); }
}

async function refreshAll() {
    updateJoinCount();
    classes = (await api('/api/teacher/classes')).classes;
    await loadStudents();
}

async function init() {
    content = await initPage('students', 'Students', 'Add, edit and search student records');
    if (!content) return;
    try { classes = (await api('/api/teacher/classes')).classes; } catch (e) { handleApiError(e); return; }
    renderShell();
    updateJoinCount();

    let timer;
    content.addEventListener('input', e => {
        if (e.target.id === 'search') { filters.search = e.target.value.trim(); clearTimeout(timer); timer = setTimeout(loadStudents, 250); }
    });
    content.addEventListener('change', e => {
        if (e.target.id === 'fClass') { filters.class_id = e.target.value; filters.section_id = ''; fillSectionFilter(); loadStudents(); }
        if (e.target.id === 'fSec') { filters.section_id = e.target.value; loadStudents(); }
        if (e.target.id === 'fLow') { filters.low = e.target.checked; loadStudents(); }
    });
    content.addEventListener('click', async e => {
        if (e.target.id === 'addStudent') return studentForm(null);
        if (e.target.id === 'bulkAdd') return bulkDialog();
        if (e.target.closest('#joinReq')) return joinRequestsDialog();
        if (e.target.id === 'emailLow') return emailAllDialog();
        const btn = e.target.closest('[data-act]'); if (!btn) return;
        const st = students.find(s => String(s.id) === btn.closest('tr').dataset.id);
        if (btn.dataset.act === 'details') return showStudent(st.id);
        if (btn.dataset.act === 'edit') studentForm(st);
        if (btn.dataset.act === 'resetface') {
            if (!await confirmDialog(`Reset the saved face of ${st.name}?\nTheir profile picture (taken from the old face scan) is removed too. They scan their face again the next time they join a session, which makes a new picture.`, 'Reset face')) return;
            try { await api(`/api/teacher/students/${st.id}/reset-face`, { method: 'POST' }); toast('Face reset.', 'success'); await loadStudents(); } catch (err) { handleApiError(err); }
        }
        if (btn.dataset.act === 'resetpw') {
            if (!await confirmDialog(`Make a new password for ${st.name}?\nThe old one stops working. You will see the new one once - give it to the student (they can change it after logging in).`, 'New password')) return;
            try { const r = await api(`/api/teacher/students/${st.id}/reset-password`, { method: 'POST' }); showCredentials([{ roll_no: st.roll_no, name: r.name, email: r.email, password: r.password }], 'New password'); } catch (err) { handleApiError(err); }
        }
        if (btn.dataset.act === 'email') emailWarning({ student_id: st.id, email: st.email, subject: st.warning_subject, body: st.warning_body });
        if (btn.dataset.act === 'del') {
            if (!await confirmDialog(`Remove ${st.name} (${st.roll_no}) from ${st.class_name} - ${st.section_name}?\nTheir attendance records in this class are deleted. If this was their only class, their login is deleted too.`)) return;
            try { await api(`/api/teacher/students/${st.id}`, { method: 'DELETE' }); toast('Student deleted.', 'success'); await refreshAll(); }
            catch (err) { handleApiError(err); }
        }
    });
    await loadStudents();
    if (params.get('add') === '1') studentForm(null);
}
init();
