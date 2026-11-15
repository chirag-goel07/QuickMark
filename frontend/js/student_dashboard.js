// Student home: overall %, concrete advice, stats, open sessions, subjects, recent attendance, my requests.
let content;

function sessionRow(s) {
    const badge = s.marked ? '<span class="badge done">Marked present</span>'
        : s.status === 'active' ? '<span class="badge active">Attendance running</span>' : '<span class="badge waiting">Waiting room</span>';
    const action = s.marked ? ''
        : `<a class="btn ${s.joined ? 'green' : ''}" href="/student/session.html?id=${s.id}">${s.joined ? (s.status === 'active' ? 'Scan QR' : 'Open waiting room') : 'Join'}</a>`;
    return `<div class="session"><div class="info"><div class="t">${esc(s.label)}</div><div class="subtle">${esc(s.teacher_name)}</div></div>${badge}${action}</div>`;
}

async function refreshSessions() {
    try {
        const d = await api('/api/student/sessions/active');
        document.getElementById('sessions').innerHTML = d.sessions.length ? d.sessions.map(sessionRow).join('')
            : '<div class="empty">No attendance session is open right now. This list updates automatically.</div>';
    } catch (e) { onAuthError(e); }
}

function adviceCard(a, p) {
    if (!a) return '';
    if (a.status === 'ok' && a.can_miss === 0) return `<div class="advice">⚠️ You are at <b>${p.percentage}%</b> (${p.present} of ${p.total} classes) and you cannot afford a miss yet: missing even <b>one</b> more class would take you below ${p.threshold}%.</div>`;
    if (a.status === 'ok') return `<div class="advice">✅ You are at <b>${p.percentage}%</b> (${p.present} of ${p.total} classes). You can miss up to <b>${a.can_miss}</b> more class${a.can_miss === 1 ? '' : 'es'} and still stay at or above ${p.threshold}%.</div>`;
    if (a.classes_needed === null) return `<div class="advice low">⚠️ You are at <b>${p.percentage}%</b>. The required ${p.threshold}% can only be reached by a perfect record.</div>`;
    const after = Math.round(1000 * (p.present + a.classes_needed) / (p.total + a.classes_needed)) / 10;
    return `<div class="advice low">⚠️ You are at <b>${p.percentage}%</b> (${p.present} of ${p.total}). Attend the next <b>${a.classes_needed}</b> class${a.classes_needed === 1 ? '' : 'es'} in a row to reach ${p.threshold}%
        (${p.present + a.classes_needed} of ${p.total + a.classes_needed} = ${after}%).</div>`;
}

async function init() {
    content = await initStudent({ active: 'home', gate: true }); if (!content) return;
    wireRequestButtons(content, () => init());
    let p, att, rq, nt = { notifications: [] };
    try { [p, att, rq, nt] = await Promise.all([api('/api/student/profile'), api('/api/student/attendance?limit=5'), api('/api/student/requests'), api('/api/student/notifications')]); } catch (e) { onAuthError(e); return; }
    const pct = p.percentage === null ? '--' : p.percentage + '%';
    content.innerHTML = `
      <div class="card"><div class="profile">${avatarHtml(p, 60)}
        <div><div class="name">${esc(p.name)}</div><div class="subtle">Roll no. ${esc(p.roll_no)} · ${esc(p.class_name)} - ${esc(p.section_name)}</div></div>
        <div class="pct"><div class="big ${p.is_low ? 'low' : 'ok'}">${pct}</div><div class="subtle">${p.total ? `${p.present} of ${p.total} classes` : 'No classes recorded yet'}</div></div></div></div>
      ${nt.notifications.length ? `<div class="card"><h3>Notifications${nt.unread ? ` <span class="pill">${nt.unread} new</span>` : ''}</h3>${nt.notifications.slice(0, 5).map(n => `<div class="advice ${n.kind === 'low_attendance' ? 'low' : ''}" style="${n.is_read ? 'opacity:.7' : ''}">${n.kind === 'low_attendance' ? '⚠️' : '📥'} ${esc(n.message)} <span class="subtle">${esc((n.created_at || '').slice(0, 10))}</span></div>`).join('')}</div>` : ''}
      ${p.require_face && !p.face_enrolled ? '<div class="warn">🙂 Your face is not set up yet, so you cannot join sessions. <a href="/student/face_setup.html">Set it up now</a></div>' : ''}
      ${adviceCard(att.advice, { ...p, percentage: att.percentage })}
      <div class="tiles-s">
        <div class="tile-s g"><div class="n">${att.present}</div><div class="l">Present</div></div>
        <div class="tile-s r"><div class="n">${att.absent}</div><div class="l">Absent</div></div>
        <div class="tile-s b"><div class="n">${att.total}</div><div class="l">Sessions</div></div>
        <div class="tile-s o"><div class="n">${att.this_month.present}/${att.this_month.total}</div><div class="l">This month${att.streak >= 2 ? ` · 🔥 ${att.streak} in a row` : ''}</div></div></div>
      <div class="card"><h3>Attendance sessions</h3><div id="sessions"><div class="empty">Loading...</div></div></div>
      <div class="card"><h3>Subject-wise attendance</h3>${subjectCard(att.subjects, att.threshold)}</div>
      <div class="card"><h3>Recent attendance</h3>${historyTable(att.history)}<a class="link-more" href="/student/history.html">View full history →</a></div>
      <div class="card"><h3>My requests</h3>${requestsList(rq.requests.slice(0, 3))}${rq.requests.length > 3 ? '<a class="link-more" href="/student/history.html">See all requests →</a>' : ''}</div>
      <div class="card"><a class="btn-ghost a-btn" style="text-decoration:none;display:inline-block" href="/student/join.html">+ Join another class with a code</a></div>`;
    if (nt.unread) api('/api/student/notifications/read', { method: 'POST' }).catch(() => {});
    await refreshSessions();
    setInterval(refreshSessions, 4000);
}
init();
