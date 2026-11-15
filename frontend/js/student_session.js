// Student side of one attendance session:
//   join (face check first when the teacher requires it) -> waiting room -> scan the teacher's QR.
// Face SETUP is done once after the first login (face_setup.html), never in the middle of a session.
// If something fails, the student can send a request AFTER the session has ended.
const sessionId = Number(new URLSearchParams(location.search).get('id'));
let content, info, scanner = null, scanning = false, busy = false, sock = null, faceActive = false;
const $ = id => document.getElementById(id);
const setHtml = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };     // never throws if the page was redrawn

const afterNote = '<div class="note">Problems joining or scanning? Don\'t worry: once the session has ended you can send your teacher a request from <a href="/student/history.html">Attendance</a> (“Request correction”).</div>';

// ------------------------------------------------------------------ request (only after the session ended)
function requestBlock() {
    if (info.my_status === 'present') return '';
    if (info.my_request === 'pending') return '<div class="note pending">📨 Request sent. Waiting for your teacher to decide. This page updates by itself.</div>';
    if (info.my_request === 'rejected') return '<div class="note bad">Your teacher declined your request. Please speak to them.</div>';
    if (info.status === 'ended' && info.can_request) return '<div class="reqbox"><button class="btn ghost full" id="askBtn">My attendance was not marked — ask my teacher</button></div>';
    return '';
}

// ------------------------------------------------------------------ page states
function render() {
    const back = '<div style="text-align:center;margin-top:14px"><a class="btn ghost" href="/student/dashboard.html">Back to dashboard</a></div>';
    let body;
    if (info.my_status === 'present') {
        body = `<div class="state-box"><div class="icon">✅</div><h2>Attendance marked</h2><div class="subtle">${info.my_request === 'approved' ? 'Your teacher accepted your request. You are present.' : 'You are present for this session.'}</div></div>${back}`;
    } else if (info.status === 'ended') {
        body = `<div class="state-box"><div class="icon">⏹️</div><h2>Session ended</h2><div class="subtle">${info.my_status === 'absent' ? 'You were marked absent.' : 'This session is over.'}</div></div>${requestBlock()}${back}`;
    } else if (info.status === 'cancelled') {
        body = `<div class="state-box"><div class="icon">🚫</div><h2>Session cancelled</h2></div>${back}`;
    } else if (!info.joined) {
        if (info.face_required && !info.face_enrolled) {
            body = `<div class="state-box"><div class="icon">🙂</div><h2>Set up your face first</h2><div class="subtle">This class checks your face before you join. It only takes a moment and is done once.</div></div>
                    <a class="btn full" href="/student/face_setup.html?next=${encodeURIComponent(location.pathname + location.search)}">Set up my face</a>${afterNote}`;
        } else {
            body = `<div class="state-box"><div class="icon">${info.face_required ? '🙂' : '👋'}</div><h2>${esc(info.label)}</h2>
                    <div class="subtle">${info.face_required ? 'Your face will be checked first, then you join the waiting room.' : 'Join to take part in this attendance session.'}</div></div>
                    <button class="btn full" id="joinBtn">${info.face_required ? 'Check face &amp; join session' : 'Join session'}</button>${afterNote}`;
        }
    } else if (info.status === 'waiting') {
        body = `<div class="state-box"><div class="icon pulse">⏳</div><h2>You're in the waiting room</h2>
                <div class="subtle">Waiting for the teacher to start attendance. Keep this page open — it will update by itself.</div></div>`;
    } else {   // active + joined: scanner
        body = `<div class="state-box"><div class="icon">📷</div><h2>Attendance has started</h2><div class="subtle">Scan the QR code on the teacher's screen.</div></div>
                <div id="reader"></div><div id="result"></div>
                <button class="btn green full" id="scanBtn">Open scanner</button>${afterNote}`;
    }
    content.innerHTML = `<div class="card"><h3>${esc(info.label)}</h3><div id="main">${body}</div></div>`;
    if ($('joinBtn')) $('joinBtn').onclick = startJoin;
    if ($('scanBtn')) $('scanBtn').onclick = openScanner;
    if ($('askBtn')) $('askBtn').onclick = () => requestDialog(sessionId, info.label, () => reload(true));
}

async function reload(forceRender) {
    try { info = await api(`/api/student/sessions/${sessionId}`); }
    catch (e) { if (e.status === 403 && info) { info.status = 'cancelled'; } else { onAuthError(e); return; } }
    if (info.status !== 'active' || info.my_status) await stopScanner();
    if (faceActive && (info.my_status || info.joined || info.status === 'ended' || info.status === 'cancelled')) await cleanupFace();
    if (!scanning && !faceActive) render();
}

// ------------------------------------------------------------------ joining (with or without a face check)
async function plainJoin() {
    const b = $('joinBtn'); if (b) b.disabled = true;
    try { await api(`/api/student/sessions/${sessionId}/join`, { method: 'POST' }); toast('Joined the session.', 'success'); await reload(); }
    catch (e) {
        if (e.code === 'face_required') { info.face_required = true; return startJoin(); }
        toast(e.message, 'error'); if (b) b.disabled = false;
    }
}

async function cleanupFace() { FaceScan.stopCamera($('faceVideo')); faceActive = false; }

function facePanel() {
    setHtml('main', `<div class="state-box"><div class="icon">🙂</div><h2>Face check</h2></div>
        <div class="facebox"><video id="faceVideo" autoplay muted playsinline></video></div>
        <div id="faceMsg"></div><div id="faceActions"></div>${afterNote}`);
}
const faceMsg = (text, cls) => setHtml('faceMsg', `<div class="note ${cls || ''}">${text}</div>`);
const faceButtons = html => setHtml('faceActions', html);
const cancelBtn = '<button class="btn ghost" id="faceCancel">Cancel</button>';
function wireCancel() { const c = $('faceCancel'); if (c) c.onclick = async () => { await cleanupFace(); render(); }; }
const retryRow = '<div class="btn-row"><button class="btn" id="faceRetry">Try again</button></div>';

async function startJoin() {
    if (!info.face_required) return plainJoin();
    faceActive = true; facePanel();
    if (!window.isSecureContext) { faceMsg('The camera only works on a secure connection. Ask your teacher to start the server with HTTPS (see README).', 'bad'); faceButtons(cancelBtn); wireCancel(); return; }
    faceMsg('Loading the face scanner…');
    try { await FaceScan.load(); } catch (e) { faceMsg('Could not load the face scanner: ' + esc(String(e)), 'bad'); faceButtons(retryRow); if ($('faceRetry')) $('faceRetry').onclick = startJoin; return; }
    try { await FaceScan.startCamera($('faceVideo')); }
    catch (e) {
        faceMsg(/Permission|NotAllowed/i.test(String(e)) ? 'Camera permission was denied. Allow the camera in your browser settings and try again.' : 'Could not start the camera: ' + esc(String(e)), 'bad');
        faceButtons(retryRow + cancelBtn); if ($('faceRetry')) $('faceRetry').onclick = startJoin; wireCancel(); return;
    }
    verifyFace();
}

async function verifyFace() {
    faceMsg('Looking for your face… hold still.'); faceButtons(cancelBtn); wireCancel();
    const d = await FaceScan.findFace($('faceVideo'), 12000, () => !faceActive);
    if (!faceActive) return;
    if (!d) { faceMsg('No face found. Move to a well-lit place and face the camera.', 'bad'); faceButtons(retryRow); if ($('faceRetry')) $('faceRetry').onclick = verifyFace; return; }
    faceMsg('Checking…');
    try {
        await api(`/api/student/sessions/${sessionId}/join-face`, { method: 'POST', body: { descriptor: d } });
        await cleanupFace(); toast('Face verified. You joined the waiting room.', 'success'); await reload(true);
    } catch (e) {
        if (e.code === 'not_enrolled') { await cleanupFace(); info.face_enrolled = false; return render(); }
        faceMsg(esc(e.message), 'bad');
        faceButtons(e.code === 'face_locked' ? cancelBtn : retryRow); if ($('faceRetry')) $('faceRetry').onclick = verifyFace; wireCancel();
    }
}

// ------------------------------------------------------------------ QR scanner
function showResult(ok, msg) { setHtml('result', `<div class="result ${ok ? 'ok' : 'bad'}">${esc(msg)}</div>`); }

async function openScanner() {
    if (!window.isSecureContext) {
        showResult(false, 'The camera only works on a secure connection. Ask your teacher to start the server with HTTPS (see README).');
        return;
    }
    const btn = $('scanBtn'); btn.disabled = true; btn.textContent = 'Starting camera...';
    scanning = true;       // set BEFORE the camera starts: the 3-second refresh must not redraw the page (and delete the camera box) while the permission prompt is open
    try {
        scanner = new Html5Qrcode('reader');
        await scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 240, height: 240 } }, onDecoded, () => {});
        btn.style.display = 'none'; showResult(true, 'Point the camera at the QR code.');
    } catch (e) {
        scanner = null; scanning = false; if ($('scanBtn')) { $('scanBtn').disabled = false; $('scanBtn').textContent = 'Open scanner'; }
        showResult(false, /Permission|NotAllowed/i.test(String(e)) ? 'Camera permission was denied. Allow the camera in your browser settings and try again.' : 'Could not start the camera: ' + e);
    }
}

async function stopScanner() {
    if (scanner) { try { await scanner.stop(); scanner.clear(); } catch (e) { /* already stopped */ } }
    scanner = null; scanning = false;
}

async function onDecoded(text) {
    if (busy) return;
    busy = true;
    try {
        const r = await api('/api/student/attendance/scan', { method: 'POST', body: { token: text } });
        await stopScanner(); await reload(true); toast(r.message, 'success');
    } catch (e) {
        if (/already marked/i.test(e.message)) { await stopScanner(); await reload(true); }
        else { showResult(false, e.message); await new Promise(r => setTimeout(r, 1500)); }   // keep scanning, brief pause
    }
    busy = false;
}

function connectLive() {
    sock = io();
    sock.on('connect', () => sock.emit('watch', { session_id: sessionId }));
    sock.on('status', () => reload());            // waiting -> active -> ended, and the teacher's decisions
}

async function init() {
    content = await initStudent({ active: 'home' }); if (!content) return;
    await reload(true); if (!info) return;
    connectLive();
    setInterval(() => { if (!scanning && !faceActive && info.status !== 'ended' && !info.my_status) reload(); }, 3000);   // safety net if the socket drops
}
init();
