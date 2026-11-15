// First login: set up the face once, before any session. The small photo taken during this scan becomes the profile picture automatically;
// the student cannot upload or change a picture afterwards (a teacher's "Reset face" is the only way to redo it).
let content, working = false, info = null;
const $ = id => document.getElementById(id);
// "Not now": stop redirecting this browser session to face setup, so a student with a broken camera can still use the rest of the app.
function skipFace() { sessionStorage.setItem('qm_face_skip', '1'); }
const next = (() => { const n = new URLSearchParams(location.search).get('next'); return n && n.startsWith('/student/') ? n : '/student/dashboard.html'; })();
const msg = (html, cls) => { const el = $('fsMsg'); if (el) el.innerHTML = html ? `<div class="note ${cls || ''}">${html}</div>` : ''; };
const buttons = html => { const el = $('fsBtns'); if (el) el.innerHTML = html; };

function frame(inner) {
    content.innerHTML = `<div class="card">${inner}</div>`;
}

function showFaceStep() {
    frame(`<div class="state-box"><div class="icon">🙂</div><h2>Welcome, ${esc(QM_ME.name.split(' ')[0])}!</h2>
        <div class="subtle">Before you take attendance, QuickMark needs to know your face once. Later it only checks that it is really you.</div></div>
        <div class="facebox"><video id="fsVideo" autoplay muted playsinline></video></div>
        <div id="fsMsg"><div class="note"><b>Your privacy:</b> QuickMark keeps <b>128 numbers</b> that describe your face, plus <b>one small photo</b> from this scan that becomes your profile picture. The live camera video never leaves your device. <b>You cannot change the picture later</b> - only your teacher can reset it. Your teacher can also delete the numbers at any time.</div></div>
        <div id="fsBtns"><div class="btn-row"><button class="btn green" id="fsStart">I agree — start face setup</button><a class="btn ghost" href="/student/profile.html" onclick="skipFace()">Not now</a></div></div>`);
    $('fsStart').onclick = runEnrollment;
}

async function runEnrollment() {
    if (working) return; working = true;
    if (!window.isSecureContext) { msg('The camera only works on a secure connection. Ask your teacher to start the server with HTTPS (see README).', 'bad'); working = false; return; }
    buttons(''); msg('Loading the face scanner…');
    try { await FaceScan.load(); } catch (e) { msg('Could not load the face scanner: ' + esc(String(e)), 'bad'); return retry(); }
    try { await FaceScan.startCamera($('fsVideo')); }
    catch (e) { msg(/Permission|NotAllowed/i.test(String(e)) ? 'Camera permission was denied. Allow the camera in your browser settings, then try again.' : 'Could not start the camera: ' + esc(String(e)), 'bad'); return retry(); }
    const samples = []; let photo = null;
    for (let i = 1; i <= 3; i++) {
        msg(`Look straight at the camera… capturing ${i} of 3`);
        const d = await FaceScan.findFace($('fsVideo'), 15000);
        if (!d) { msg('No face found. Move to a well-lit place, face the camera and try again.', 'bad'); FaceScan.stopCamera($('fsVideo')); return retry(); }
        if (i === 2) { try { photo = await FaceScan.snapshotJpeg($('fsVideo')); } catch (e) { photo = null; } }      // the profile picture: the face seen in the 2nd capture
        samples.push(d); await new Promise(r => setTimeout(r, 500));
    }
    FaceScan.stopCamera($('fsVideo'));
    if (!photo) { msg('Could not take your picture. Try again.', 'bad'); return retry(); }
    try {
        await api('/api/student/face/enroll', { method: 'POST', body: { samples, photo: await blobToBase64(photo) } });
        toast('Face saved.', 'success'); QM_ME.needs_face_setup = false; working = false; await showDone();
    }
    catch (e) { msg(esc(e.message), 'bad'); retry(); }
}
function retry() { working = false; buttons('<div class="btn-row"><button class="btn" id="fsRetry">Try again</button><a class="btn ghost" href="/student/profile.html" onclick="skipFace()">Not now</a></div>'); $('fsRetry').onclick = runEnrollment; }

async function blobToBase64(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer()); let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
}

async function showDone() {
    try { info = await api('/api/student/profile'); QM_ME = { ...QM_ME, ...info }; } catch (e) { /* the picture just may not show yet */ }
    frame(`<div class="state-box"><div class="icon">✅</div><h2>Your face is set up</h2>
        <div class="subtle">The photo from this scan is now your profile picture. It cannot be changed by you; if it ever needs redoing, your teacher can reset your face.</div></div>
        <div id="prev" style="text-align:center">${avatarHtml(QM_ME, 120).replace('class="av"', 'class="av preview-av"')}</div>
        <div class="btn-row"><button class="btn green" id="fsDone">Continue</button></div>`);
    $('fsDone').onclick = () => { location.href = next; };
}

async function init() {
    content = await initStudent({ noGate: true, active: 'profile' }); if (!content) return;
    try { info = await api('/api/student/profile'); } catch (e) { return onAuthError(e); }
    QM_ME = { ...QM_ME, ...info };
    if (info.face_enrolled) { location.href = next; return; }          // already set up: nothing to do here
    showFaceStep();
}
init();
