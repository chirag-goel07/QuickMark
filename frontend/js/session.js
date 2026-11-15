// Waiting room -> QR screen -> summary. Everything shown here comes from the server (REST + Socket.IO).
const sessionId = Number(new URLSearchParams(location.search).get('id'));
let content, shown = null, timeOffset = 0, expiresAt = null, sock = null, liveOn = false;

const $ = id => document.getElementById(id);
function setLive(on) {
    liveOn = on; const l = $('live');
    if (l) { l.textContent = on ? '● Live' : '● Reconnecting...'; l.className = 'live-dot ' + (on ? 'on' : 'off'); }
}
const VIA = { teacher: ' ✋', request: ' ✉' };
const peopleVia = (list, cls) => list.length ? list.map(p => `<span class="person ${cls || ''}" title="${p.via === 'teacher' ? 'Marked by you' : p.via === 'request' ? 'Request approved' : 'QR scan'}">${esc(p.name)}<small>${esc(p.roll_no)}${VIA[p.via] || ''}</small></span>`).join('') : '<span class="subtle">Nobody yet</span>';
function requestsCard(st) {
    return `<div class="card" id="reqCard" style="display:none"><h3 class="card-title">✉ Requests from students <span id="reqCount"></span></h3>
        <div class="subtle" style="margin-bottom:8px">These students could not join or scan. Accepting marks them present.</div><div id="reqList"></div></div>`;
}
function updateRequests(st) {
    const card = $('reqCard'); if (!card) return;
    card.style.display = st.requests.length ? 'block' : 'none';
    $('reqCount').textContent = st.requests.length ? `(${st.requests.length})` : '';
    $('reqList').innerHTML = st.requests.map(r => `<div class="req-row">${stuAvatar(r.student_id, r.name, r.has_avatar, r.avatar_v, 44)}<div class="req-info"><b>${esc(r.name)}</b> <span class="subtle">${esc(r.roll_no)}</span>
        ${r.message ? `<div class="req-msg">“${esc(r.message)}”</div>` : ''}</div>
        <button class="btn-primary btn-sm" data-req-accept="${r.id}">Accept</button><button class="btn-danger btn-sm" data-req-reject="${r.id}">Reject</button></div>`).join('');
}
const people = (list, cls) => list.length ? list.map(p => `<span class="person ${cls || ''}">${esc(p.name)}<small>${esc(p.roll_no)}</small></span>`).join('') : '<span class="subtle">Nobody yet</span>';

function layout(st) {
    if (st.status === 'waiting') {
        content.innerHTML = `<div class="center-card" style="display:flex;flex-direction:column;gap:18px">
          <div class="card"><div class="session-top"><h2>${esc(st.label)}</h2><span class="status-badge waiting">Waiting for teacher to start</span>
            <span class="live-dot" id="live">● connecting...</span></div></div>
          <div class="card"><h3 class="card-title">Waiting Room</h3>
            <div class="tiles">
              <div class="tile blue"><div class="num" id="total">-</div><div class="lbl">Total Students</div></div>
              <div class="tile green"><div class="num" id="joined">-</div><div class="lbl">Students Joined</div></div>
              <div class="tile orange"><div class="num" id="pct">-</div><div class="lbl">Joined Percentage</div></div>
            </div>
            <div class="progress" style="margin-top:16px"><div id="bar" style="width:0"></div></div>
            <div class="chips-label">Joined students</div><div class="people" id="joinedList"></div>
          </div>
          ${requestsCard(st)}
          <div class="hidden-note">🔒 The QR code stays hidden until you press START ATTENDANCE. Students scan only after that.</div>
          <button class="btn-start" id="start">START ATTENDANCE</button>
          <div style="text-align:center"><button class="btn-danger" id="cancel">Cancel this session</button></div></div>`;
        $('start').onclick = onStart; $('cancel').onclick = onCancel;
    } else if (st.status === 'active') {
        content.innerHTML = `<div class="center-card" style="display:flex;flex-direction:column;gap:18px">
          <div class="card"><div class="session-top"><h2>${esc(st.label)}</h2><span class="status-badge active">Attendance running</span>
            <span class="live-dot" id="live">● connecting...</span></div></div>
          <div class="card qr-stage"><div class="subtle">Students: open QuickMark on your phone and scan this code</div>
            <div class="qr-box" id="qrBox"><span class="qr-wait">Getting QR code...</span></div>
            <div class="rotate-bar"><div id="rot"></div></div>
            <div class="subtle">The code changes every 3 seconds</div>
            <div style="margin-top:12px" class="subtle">Time remaining</div><div class="timer" id="timer">--:--</div></div>
          <div class="card"><div class="tiles">
              <div class="tile green"><div class="num"><span id="present">0</span> / <span id="total">0</span></div><div class="lbl">Present</div></div>
              <div class="tile blue"><div class="num" id="joined">0</div><div class="lbl">Joined</div></div></div>
            <div class="progress green" style="margin-top:16px"><div id="bar" style="width:0"></div></div>
            <div class="chips-label">Marked present <span class="subtle">(✉ = request approved)</span></div><div class="people" id="presentList"></div></div>
          ${requestsCard(st)}
          <button class="btn-danger solid" style="padding:16px;font-size:18px;border-radius:10px" id="end">■ End Attendance</button></div>`;
        $('end').onclick = onEnd;
    } else {
        content.innerHTML = `<div class="center-card" style="display:flex;flex-direction:column;gap:18px">
          <div class="card"><div class="session-top"><h2>${esc(st.label)}</h2><span class="status-badge ended">Attendance ended</span></div></div>
          <div class="card"><h3 class="card-title">Final Attendance</h3>
            <div class="tiles">
              <div class="tile blue"><div class="num" id="total">0</div><div class="lbl">Total</div></div>
              <div class="tile green"><div class="num" id="present">0</div><div class="lbl">Present</div></div>
              <div class="tile orange"><div class="num" id="absent">0</div><div class="lbl">Absent</div></div></div>
            <div class="progress green" style="margin-top:16px"><div id="bar" style="width:0"></div></div>
            <div class="subtle" id="pctText"></div>
            <div class="chips-label">Present</div><div class="people" id="presentList"></div>
            <div class="chips-label">Absent</div><div class="people" id="absentList"></div></div>
          ${requestsCard(st)}
          <div class="row"><a class="btn-ghost" style="text-decoration:none;text-align:center;flex:1;padding:12px" href="/teacher/history.html?open=${st.id}">✎ Edit attendance (section-wise)</a></div>
          <div class="row"><a class="btn-primary" style="text-decoration:none;text-align:center;flex:1" href="/teacher/take_attendance.html">Start another session</a>
            <a class="btn-ghost" style="text-decoration:none;text-align:center;flex:1;padding:12px" href="/teacher/dashboard.html">Back to Dashboard</a></div></div>`;
    }
    shown = st.status;
    setLive(liveOn);
}

function update(st) {
    if (shown !== st.status) layout(st);
    if (st.status === 'waiting') {
        $('total').textContent = st.total; $('joined').textContent = st.joined; $('pct').textContent = st.joined_pct + '%';
        $('bar').style.width = st.joined_pct + '%'; $('joinedList').innerHTML = people(st.joined_students); updateRequests(st);
    } else if (st.status === 'active') {
        $('total').textContent = st.total; $('present').textContent = st.present; $('joined').textContent = st.joined;
        $('bar').style.width = (st.total ? 100 * st.present / st.total : 0) + '%'; $('presentList').innerHTML = peopleVia(st.present_students, 'present'); updateRequests(st);
        expiresAt = st.expires_at; timeOffset = st.server_time - Date.now() / 1000;
    } else {
        $('total').textContent = st.total; $('present').textContent = st.present; $('absent').textContent = st.absent;
        $('bar').style.width = st.present_pct + '%'; $('pctText').textContent = `${st.present_pct}% attendance`;
        $('presentList').innerHTML = peopleVia(st.present_students, 'present'); $('absentList').innerHTML = peopleVia(st.absent_students, 'absent'); updateRequests(st);
        if (sock) sock.disconnect();
    }
}

function showQr(d) {
    const box = $('qrBox'); if (!box) return;
    box.innerHTML = d.svg;
    const bar = $('rot'); bar.classList.remove('run'); void bar.offsetWidth; bar.classList.add('run');   // restart the 3s bar
}

setInterval(() => {
    const t = $('timer'); if (!t || expiresAt === null) return;
    const left = Math.max(0, Math.round(expiresAt - (Date.now() / 1000 + timeOffset)));
    t.textContent = String(Math.floor(left / 60)).padStart(2, '0') + ':' + String(left % 60).padStart(2, '0');
}, 500);

async function onStart() {
    const b = $('start'); b.disabled = true;
    try { await api(`/api/teacher/sessions/${sessionId}/start`, { method: 'POST' }); }
    catch (e) { toast(e.message, 'error'); b.disabled = false; }
}
async function onEnd() {
    if (!await confirmDialog('End attendance now?\nStudents who have not scanned will be marked absent and further scans will be rejected.', 'End Attendance')) return;
    try { update(await api(`/api/teacher/sessions/${sessionId}/end`, { method: 'POST' })); toast('Attendance saved.', 'success'); }
    catch (e) { toast(e.message, 'error'); }
}
async function onCancel() {
    if (!await confirmDialog('Cancel this session? Nothing will be saved.', 'Cancel session')) return;
    try { await api(`/api/teacher/sessions/${sessionId}/cancel`, { method: 'POST' }); location.href = '/teacher/take_attendance.html'; }
    catch (e) { toast(e.message, 'error'); }
}

function connectLive() {
    sock = io();
    sock.on('connect', () => { setLive(true); sock.emit('watch', { session_id: sessionId }, r => { if (!r || !r.ok) toast('Could not start live updates.', 'error'); }); });
    sock.on('disconnect', () => setLive(false));
    sock.on('state', update);
    sock.on('qr', showQr);
}

async function init() {
    content = await initPage('attendance', 'Attendance Session', 'Live attendance');
    if (!content) return;
    try { update(await api(`/api/teacher/sessions/${sessionId}`)); }
    catch (e) { content.innerHTML = `<div class="card center-card"><div class="empty">${esc(e.message)} <a href="/teacher/take_attendance.html">Back</a></div></div>`; return; }
    connectLive();
    content.addEventListener('click', async e => {
        const acc = e.target.closest('[data-req-accept]'), rej = e.target.closest('[data-req-reject]');
        try {
            if (acc || rej) {
                const id = (acc || rej).dataset.reqAccept || (acc || rej).dataset.reqReject;
                (acc || rej).disabled = true;
                await api(`/api/teacher/sessions/requests/${id}/${acc ? 'accept' : 'reject'}`, { method: 'POST' });
                toast(acc ? 'Accepted. The student is now present.' : 'Request rejected.', 'success');
                if (shown === 'ended') update(await api(`/api/teacher/sessions/${sessionId}`));
            }
        } catch (err) { toast(err.message, 'error'); }
    });
}
init();
