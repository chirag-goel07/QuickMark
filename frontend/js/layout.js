// Builds the sidebar + header around a page and returns the content element.
// Usage:  const content = await initPage('students', 'Students', 'Manage student records');
const NAV = [
    ['dashboard', '🏠', 'Dashboard', '/teacher/dashboard.html'],
    ['classes', '🎓', 'Classes', '/teacher/classes.html'],
    ['students', '👥', 'Students', '/teacher/students.html'],
    ['attendance', '▦', 'Take Attendance', '/teacher/take_attendance.html'],
    ['history', '🕘', 'Attendance History', '/teacher/history.html'],
    ['reports', '📊', 'Reports', '/teacher/reports.html'],
    ['settings', '⚙️', 'Settings', '/teacher/settings.html'],
];

async function initPage(activeKey, title, subtitle) {
    let me;
    try { me = await api('/api/auth/me'); if (me.role !== 'teacher') throw new Error('no'); }
    catch (e) { location.href = '/teacher/login.html'; return null; }

    document.body.innerHTML = `<div class="layout">
      <aside class="sidebar">
        <div class="brand-row"><div class="brand-logo">⚡</div>
          <div><div class="brand">QuickMark</div><div class="brand-sub">Smart QR-Based Attendance System</div></div></div>
        ${NAV.map(n => `<a class="nav-btn${n[0] === activeKey ? ' active' : ''}" href="${n[3]}">${n[1]}&nbsp;&nbsp; ${n[2]}</a>`).join('')}
        <a class="nav-btn" href="#" id="logout">🚪&nbsp;&nbsp; Logout</a>
        <div class="side-spacer"></div>
        <div class="side-tag">Better Attendance<br>Builds a Brighter Future</div>
        <div class="side-foot">⚡ <b>QuickMark</b></div>
      </aside>
      <div class="main">
        <header class="header"><div><div class="greet">${esc(title)}</div><div class="subtle">${esc(subtitle || '')}</div></div>
          <div class="header-grow"></div>
          <div class="user"><div class="avatar">👤</div><div><div class="user-name">${esc(me.name)}</div><div class="subtle">Teacher</div></div></div>
        </header>
        <div class="page-body" id="content"><div class="loading">Loading...</div></div>
      </div></div>`;

    document.getElementById('logout').addEventListener('click', async e => {
        e.preventDefault();
        if (!await confirmDialog('Log out of QuickMark?', 'Log out')) return;
        await api('/api/auth/logout', { method: 'POST' });
        location.href = '/teacher/login.html';
    });
    return document.getElementById('content');
}

// Pages call this when an API request fails with 401/403 (session expired).
function handleApiError(e) {
    if (e.status === 401 || e.status === 403) { location.href = '/teacher/login.html'; return; }
    toast(e.message, 'error');
}
