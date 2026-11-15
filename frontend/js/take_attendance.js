// Step 1 of attendance: choose class + section, then create a session (this opens the waiting room).
async function init() {
    const content = await initPage('attendance', 'Take Attendance', 'Select a class and section, then open the waiting room');
    if (!content) return;
    const params = new URLSearchParams(location.search);
    let classes, cur;
    try {
        classes = (await api('/api/teacher/classes')).classes;
        cur = await api('/api/teacher/sessions/current');
    } catch (e) { handleApiError(e); return; }

    const banner = cur.session ? `<div class="resume-banner"><div class="grow"><b>You have an unfinished session:</b> ${esc(cur.session.label)}
        (${cur.session.status === 'waiting' ? 'waiting room' : 'attendance running'})</div>
        <a class="btn-primary" style="text-decoration:none" href="/teacher/session.html?id=${cur.session.id}">Resume</a></div>` : '';

    const usable = classes.filter(c => c.sections.length);
    if (!usable.length) {
        content.innerHTML = banner + `<div class="card center-card"><div class="empty">You need a class with at least one section and some students first.
            <a href="/teacher/classes.html">Go to Classes</a></div></div>`;
        return;
    }
    const startClass = usable.find(c => String(c.id) === params.get('class')) || usable[0];
    content.innerHTML = banner + `
      <div class="card center-card"><h3 class="card-title">Start Section Attendance</h3>
        <div class="error-msg" id="err"></div>
        <div class="form-grid">
          <div class="field"><label>Class</label><select id="cls">${usable.map(c => `<option value="${c.id}"${c.id === startClass.id ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select></div>
          <div class="field"><label>Section</label><select id="sec"></select></div>
          <div class="field"><label>Subject (optional)</label><select id="sub"></select></div>
          <div class="field"><label>Session duration (minutes)</label><input type="text" id="dur" value="${cur.default_duration}"></div>
        </div>
        <button class="btn-primary" id="go" ${cur.session ? 'disabled title="Finish your open session first"' : ''}>▶&nbsp; Start Attendance</button>
        <div class="subtle" style="margin-top:10px">This opens a waiting room. The QR code is shown only after you press START ATTENDANCE there.</div>
      </div>`;

    const clsSel = document.getElementById('cls'), secSel = document.getElementById('sec'), subSel = document.getElementById('sub');
    function fill() {
        const c = usable.find(x => String(x.id) === clsSel.value);
        secSel.innerHTML = c.sections.map(s => `<option value="${s.id}"${String(s.id) === params.get('section') ? ' selected' : ''}>${esc(s.name)} (${s.student_count} students)</option>`).join('');
        subSel.innerHTML = '<option value="">No subject</option>' + c.subjects.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
    }
    clsSel.addEventListener('change', fill); fill();

    document.getElementById('go').addEventListener('click', async e => {
        const btn = e.currentTarget, err = document.getElementById('err');
        err.classList.remove('show'); btn.disabled = true;
        try {
            const r = await api('/api/teacher/sessions', { method: 'POST', body: {
                type: 'normal', section_id: Number(secSel.value), subject_id: subSel.value ? Number(subSel.value) : null,
                duration_minutes: document.getElementById('dur').value } });
            location.href = '/teacher/session.html?id=' + r.id;
        } catch (ex) { err.textContent = ex.message; err.classList.add('show'); btn.disabled = false; }
    });
}
init();
