// Teacher dashboard: every number on this page comes from GET /api/teacher/dashboard.

function greeting() {
    const h = new Date().getHours();
    return h < 12 ? 'Good Morning' : h < 17 ? 'Good Afternoon' : 'Good Evening';
}

function tickClock() {
    const now = new Date();
    document.getElementById('dateLbl').textContent = '📅  ' +
        now.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
    document.getElementById('timeLbl').textContent = '🕒  ' +
        now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function statCard(color, icon, title, value, linkText, href) {
    return `<div class="stat ${color}"><div class="badge">${icon}</div>
        <div class="stat-title">${title}</div><div class="stat-value">${value}</div>
        <a class="link-btn" href="${href}">${linkText} &nbsp;→</a></div>`;
}

function actionCard(color, icon, title, desc, href) {
    return `<a class="action ${color}" href="${href}"><div class="badge" style="background:rgba(255,255,255,.65)">${icon}</div>
        <div class="action-title">${title}</div><div class="action-desc">${desc}</div><div class="action-arrow">→</div></a>`;
}

function render(d) {
    const s = d.stats;
    const overall = s.overall_attendance === null ? '--' : s.overall_attendance + '%';

    // class + section selector (options come from the database)
    const classOpts = d.classes.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
    const selector = d.classes.length
        ? `<div class="selector-row">
             <div class="field" style="flex:3"><label>Class</label><select id="classSel">${classOpts}</select></div>
             <div class="field" style="flex:2"><label>Section</label><select id="secSel"></select></div>
             <button class="btn-primary" id="loadBtn">⟳&nbsp; Load</button></div>`
        : `<div class="empty">No classes yet. <a href="/teacher/classes.html">Add your first class</a> to get started.</div>`;

    const groupHtml = d.todays_groups.length
        ? d.todays_groups.map(g => `<div class="group-box"><div class="badge">👥</div>
              <div style="flex:1">${esc(g.label)}<div class="subtle">${g.total_students} students · ${esc(g.status)}</div></div></div>`).join('')
        : `<div class="empty">No group attendance today.</div>`;

    const lowHtml = d.low_attendance.length
        ? d.low_attendance.slice(0, 5).map((st, i) => `<div class="low-row">
              <div class="initial">${esc(st.name.charAt(0).toUpperCase())}</div>
              <div class="low-info"><div class="low-name">${esc(st.name)}</div>
              <div class="low-class">${esc(st.class_name)} - ${esc(st.section_name)}</div>
              <button class="btn-ghost btn-sm" style="margin-top:6px" data-email="${i}">✉ Email Warning</button></div>
              <div class="pill">${st.percentage}%</div></div>`).join('')
          + `<button class="btn-primary btn-sm" style="width:100%;margin-top:12px" id="emailAll">✉ Email All Low-Attendance Students (${d.low_attendance.length})</button>`
        : `<div class="empty">No students below ${d.threshold}% attendance.</div>`;

    document.getElementById('body').innerHTML = `
      <div class="col-left">
        <div class="row">
          ${statCard('blue', '🎓', 'Total Classes', s.total_classes, 'View Classes', '/teacher/classes.html')}
          ${statCard('green', '👥', 'Total Students', s.total_students, 'View Students', '/teacher/students.html')}
          ${statCard('purple', '🗓️', "Today's Sessions", s.todays_sessions, 'View Sessions', '/teacher/history.html')}
          ${statCard('orange', '％', 'Overall Attendance', overall, 'View Report', '/teacher/reports.html')}
        </div>
        <div class="card"><h3 class="card-title">Select Class &amp; Section</h3>${selector}</div>
        <div class="row">
          ${actionCard('blue', '👥', 'Section-wise\nAttendance', 'Take attendance for\nan entire section', '/teacher/take_attendance.html')}
          ${actionCard('green', '👥', 'Group Attendance', 'Select specific students\nor create a group', '/teacher/group_attendance.html')}
          ${actionCard('purple', '▦', 'Generate QR Code', 'Create a QR for selected\nsection or group', '/teacher/take_attendance.html')}
        </div>
        <div class="card"><h3 class="card-title">Quick Actions</h3>
          <div class="row">
            <a class="quick" href="/teacher/classes.html">📁<br>Manage Classes</a>
            <a class="quick" href="/teacher/students.html?add=1">👤<br>Add New Student</a>
            <a class="quick" href="/teacher/reports.html">📄<br>View Reports</a>
            <a class="quick" href="/teacher/history.html">🕘<br>Attendance History</a>
          </div>
        </div>
      </div>
      <div class="col-right">
        ${requestsCard(d)}
        <div class="card"><h3 class="card-title">Today's Group Attendance</h3>${groupHtml}
          <a class="btn-primary" style="display:block;text-align:center;text-decoration:none" href="/teacher/group_attendance.html">▶&nbsp;&nbsp; Start Group Attendance</a></div>
        <div class="card">
          <div class="low-head">❗ Students with Low Attendance <a class="link-btn" href="/teacher/students.html?low=1">View All →</a></div>
          ${lowHtml}
        </div>
      </div>`;

    if (d.classes.length) wireSelector(d.classes);
    document.querySelectorAll('[data-rq-accept],[data-rq-reject]').forEach(b => b.addEventListener('click', async () => {
        const accept = b.hasAttribute('data-rq-accept'); b.disabled = true;
        try { await api(`/api/teacher/sessions/requests/${b.dataset.rqAccept || b.dataset.rqReject}/${accept ? 'accept' : 'reject'}`, { method: 'POST' });
              toast(accept ? 'Accepted. The student is now present.' : 'Request rejected.', 'success'); loadDashboard(); }
        catch (e) { toast(e.message, 'error'); b.disabled = false; }
    }));
    document.querySelectorAll('[data-email]').forEach(b => b.addEventListener('click', () => emailWarning(d.low_attendance[Number(b.dataset.email)])));
    const all = document.getElementById('emailAll'); if (all) all.addEventListener('click', emailAllDialog);
}

function requestsCard(d) {
    if (!d.requests.length) return '';
    return `<div class="card" id="reqCard"><h3 class="card-title">✉ Attendance requests (${d.requests.length})</h3>
        <div class="subtle" style="margin-bottom:6px">Students asking to be marked present. Accepting makes them present.</div>
        ${d.requests.slice(0, 5).map(r => `<div class="low-row" style="align-items:flex-start">${stuAvatar(r.student_id, r.name, r.has_avatar, r.avatar_v, 44)}<div class="low-info"><div class="low-name">${esc(r.name)} <span class="subtle">${esc(r.roll_no)}</span></div>
          <div class="low-class">${esc(r.label)} · ${esc(r.date)}${r.session_status === 'ended' ? ' · session ended' : ''}</div>
          ${r.message ? `<div class="low-class" style="font-style:italic">“${esc(r.message)}”</div>` : ''}
          <div style="margin-top:6px;display:flex;gap:6px"><button class="btn-primary btn-sm" data-rq-accept="${r.id}">Accept</button><button class="btn-danger btn-sm" data-rq-reject="${r.id}">Reject</button></div></div></div>`).join('')}
        ${d.requests.length > 5 ? `<div class="subtle" style="margin-top:8px">+ ${d.requests.length - 5} more. Open the session in Attendance History to see them.</div>` : ''}</div>`;
}

function wireSelector(classes) {
    const classSel = document.getElementById('classSel'), secSel = document.getElementById('secSel');
    const fillSections = () => {
        const c = classes.find(x => String(x.id) === classSel.value);
        secSel.innerHTML = c.sections.length
            ? c.sections.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('')
            : '<option value="">No sections</option>';
    };
    classSel.addEventListener('change', fillSections);
    fillSections();
    document.getElementById('loadBtn').addEventListener('click', () => {
        if (!secSel.value) { alert('This class has no sections yet. Add one under Classes.'); return; }
        location.href = `/teacher/take_attendance.html?class=${classSel.value}&section=${secSel.value}`;
    });
}

async function init() {
    tickClock(); setInterval(tickClock, 1000);
    document.getElementById('logout').addEventListener('click', async e => {
        e.preventDefault();
        if (!confirm('Log out of QuickMark?')) return;
        await api('/api/auth/logout', { method: 'POST' });
        location.href = '/teacher/login.html';
    });
    await loadDashboard();
}
async function loadDashboard() {
    try {
        const d = await api('/api/teacher/dashboard');
        document.getElementById('greet').textContent = `${greeting()}, ${d.teacher.name}!`;
        document.getElementById('userName').textContent = d.teacher.name;
        render(d);
    } catch (e) {
        if (e.status === 401 || e.status === 403) { location.href = '/teacher/login.html'; return; }
        document.getElementById('body').innerHTML = `<div class="loading">Could not load the dashboard: ${esc(e.message)}</div>`;
    }
}
init();
