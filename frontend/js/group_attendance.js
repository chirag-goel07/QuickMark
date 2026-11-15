// Group attendance: a group = the SECTIONS the teacher ticks (choose a class, tick its sections). No students are shown here;
// the group's students are simply everyone in those sections. Then the same waiting-room flow as section attendance.
let content, groups = [], openSession = null, defaultDuration = 10, classesData = [];

async function load() {
    try {
        const [g, cur] = await Promise.all([api('/api/teacher/groups'), api('/api/teacher/sessions/current')]);
        groups = g.groups; openSession = cur.session; defaultDuration = cur.default_duration; render();
    } catch (e) { handleApiError(e); }
}

function render() {
    const banner = openSession ? `<div class="resume-banner"><div class="grow"><b>You have an unfinished session:</b> ${esc(openSession.label)}
        (${openSession.status === 'waiting' ? 'waiting room' : 'attendance running'})</div>
        <a class="btn-primary" style="text-decoration:none" href="/teacher/session.html?id=${openSession.id}">Resume</a></div>` : '';
    const cards = groups.map(g => {
        const inUse = g.locked;
        const secs = g.sections.map(x => `<span class="chip subject" style="padding:4px 12px">${esc(x.class_name)} - ${esc(x.name)} <span class="subtle">(${x.student_count})</span></span>`).join('');
        return `<div class="card group-card" data-id="${g.id}"><div class="head">
            <h3>👥 ${esc(g.name)}</h3><span class="subtle">${g.sections.length} section${g.sections.length === 1 ? '' : 's'} · ${g.member_count} student${g.member_count === 1 ? '' : 's'}</span>
            ${inUse ? '<span class="badge-lock">In session</span>' : ''}<div class="grow"></div>
            <button class="btn-primary btn-sm" data-act="start" ${(g.member_count === 0 || openSession) ? 'disabled' : ''}>▶ Start Attendance</button>
            <button class="btn-ghost btn-sm" data-act="edit">Edit</button>
            <button class="btn-danger btn-sm" data-act="del">Delete</button></div>
            <div class="chips" style="margin-top:10px">${secs || '<span class="subtle">No sections.</span>'}</div></div>`;
    }).join('');
    content.innerHTML = banner + `
      <div class="card"><div class="toolbar">
        <div class="field" style="min-width:200px"><label>Session duration (minutes)</label><input type="text" id="dur" value="${defaultDuration}"></div>
        <div class="grow"></div><button class="btn-primary" id="addGroup">+ Create Group</button></div>
        <div class="subtle" style="margin-top:8px">Group attendance uses the same waiting room as section attendance: the QR appears only after you press START ATTENDANCE.</div></div>
      ${cards || '<div class="card"><div class="empty">No groups yet. Create a group: choose a class and tick the sections that take this attendance.</div></div>'}`;
}

// ---------- group editor: choose a class -> tick its sections (no students are listed) ----------
async function openEditor(group) {
    try { classesData = (await api('/api/teacher/classes')).classes; } catch (e) { return handleApiError(e); }    // fresh sections and counts
    if (!classesData.some(c => c.sections.length)) { toast('Create a class with sections first (Classes page).', 'error'); return; }
    let full = { name: '', sections: [], by_sections: true };
    if (group) { try { full = await api('/api/teacher/groups/' + group.id); } catch (e) { return handleApiError(e); } }

    const secInfo = new Map();                                         // section id -> {name, class_name, count}
    classesData.forEach(c => c.sections.forEach(sec => secInfo.set(sec.id, { name: sec.name, class_name: c.name, count: sec.student_count })));
    const secSel = new Set(full.sections.map(x => x.id).filter(id => secInfo.has(id)));
    const firstClass = secSel.size ? classesData.find(c => c.sections.some(x => secSel.has(x.id))) : null;
    let classId = firstClass ? String(firstClass.id) : '';

    const o = _openModal(`<h3>${group ? 'Edit Group' : 'Create Group'}</h3><div class="error-msg" id="gErr"></div>
        <div class="field"><label>Group name *</label><input type="text" id="gName" value="${esc(full.name)}" autocomplete="off"></div>
        <div class="field" style="margin:0"><label>Class</label><select id="gClass"><option value="">Choose a class...</option>${
            classesData.map(c => `<option value="${c.id}"${String(c.id) === classId ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select></div>
        <div class="step-title">Sections - tick the ones that take this attendance</div>
        <div class="sec-grid" id="gSecs"></div>
        <div class="subtle" id="gTicked" style="margin-top:10px"></div>
        ${group && !full.by_sections ? '<div class="hint" style="margin-top:8px">This group was made from individually picked students. Saving it will make it follow the whole sections ticked above.</div>' : ''}
        <div class="hint" style="margin-top:8px">You can switch the class and tick sections of other classes too. Students are not listed here - the group is everyone in the ticked sections (see them on the Students page).</div>
        <div class="foot"><button class="btn-ghost" id="gCancel">Cancel</button><button class="btn-primary" id="gSave">Save group</button></div>`);
    const $ = id => o.querySelector('#' + id);
    const label = sid => { const i = secInfo.get(sid); return i.class_name + ' - ' + i.name; };

    const drawSections = () => {
        const c = classesData.find(x => String(x.id) === classId);
        $('gSecs').innerHTML = !c ? '<div class="subtle">Choose a class to see its sections.</div>'
            : !c.sections.length ? '<div class="subtle">This class has no sections yet (Classes page).</div>'
            : c.sections.map(sec => { const n = sec.student_count, on = secSel.has(sec.id);
                return `<label class="sec-box${on ? ' on' : ''}${n ? '' : ' off'}"><input type="checkbox" data-sec="${sec.id}"${on ? ' checked' : ''}${n ? '' : ' disabled'}>
                    <b>${esc(sec.name)}</b><span class="meta">${n} student${n === 1 ? '' : 's'}</span></label>`; }).join('');
        const total = [...secSel].reduce((n, sid) => n + secInfo.get(sid).count, 0);
        $('gTicked').innerHTML = secSel.size ? `<b>Ticked:</b> ${[...secSel].map(sid => esc(label(sid))).join(', ')} <span class="subtle">· ${total} student${total === 1 ? '' : 's'} in total</span>` : 'No section ticked yet.';
    };
    $('gClass').addEventListener('change', e => { classId = e.target.value; drawSections(); });
    $('gSecs').addEventListener('change', e => {
        const sid = Number(e.target.dataset.sec); if (!sid) return;
        e.target.checked ? secSel.add(sid) : secSel.delete(sid); drawSections();
    });
    $('gCancel').onclick = () => o.remove();
    $('gSave').onclick = async () => {
        const err = $('gErr'), btn = $('gSave'); err.classList.remove('show');
        if (!secSel.size) { err.textContent = 'Tick at least one section.'; err.classList.add('show'); return; }
        btn.disabled = true;
        try {
            await api(group ? '/api/teacher/groups/' + group.id : '/api/teacher/groups', { method: group ? 'PUT' : 'POST', body: { name: $('gName').value, section_ids: [...secSel] } });
            o.remove(); toast(group ? 'Group updated.' : 'Group created.', 'success'); await load();
        } catch (e) { err.textContent = e.message; err.classList.add('show'); btn.disabled = false; }
    };
    drawSections(); $('gName').focus();
}

async function init() {
    content = await initPage('attendance', 'Group Attendance', 'Take attendance for the sections you choose');
    if (!content) return;
    content.addEventListener('click', async e => {
        if (e.target.id === 'addGroup') return openEditor(null);
        const btn = e.target.closest('[data-act]'); if (!btn) return;
        const g = groups.find(x => String(x.id) === btn.closest('.group-card').dataset.id);
        if (btn.dataset.act === 'edit') return openEditor(g);
        if (btn.dataset.act === 'del') {
            if (!await confirmDialog(`Delete group “${g.name}”?\nPast attendance records are kept.`)) return;
            try { await api('/api/teacher/groups/' + g.id, { method: 'DELETE' }); toast('Group deleted.', 'success'); await load(); } catch (err) { toast(err.message, 'error'); }
        }
        if (btn.dataset.act === 'start') {
            btn.disabled = true;
            try {
                const r = await api('/api/teacher/sessions', { method: 'POST', body: { type: 'group', group_id: g.id, duration_minutes: document.getElementById('dur').value } });
                location.href = '/teacher/session.html?id=' + r.id;
            } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
        }
    });
    load();
}
init();
