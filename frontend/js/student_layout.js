// Shared by every student page: top bar + navigation, profile picture helpers, first-login face-setup gate.
// Usage:  const content = await initStudent({ active: 'home' });
let QM_ME = null;
const STUDENT_NAV = [['home', 'Home', '/student/dashboard.html'], ['classes', 'Classes', '/student/classes.html'],
                     ['attendance', 'Attendance', '/student/history.html'], ['profile', 'Profile', '/student/profile.html']];

function initials(name) { return (name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join(''); }

// A round picture: the student's own photo, or their initials when there is none yet.
function avatarHtml(me, size) {
    size = size || 40;
    if (me.has_avatar) return `<img class="av" style="width:${size}px;height:${size}px" src="/api/student/avatar?v=${encodeURIComponent(me.avatar_v || '')}" alt="">`;
    return `<span class="av av-init" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.4)}px">${esc(initials(me.name))}</span>`;
}

async function initStudent(opts) {
    opts = opts || {};
    let me;
    try { me = await api('/api/auth/me'); if (me.role !== 'student') throw new Error('no'); }
    catch (e) { location.href = '/student/login.html'; return null; }
    // First login: the home page sends the student to face setup (not in the middle of a session).
    // "Not now" switches this off for the rest of the browser session, so a student with a broken camera can still use everything else.
    if (me.needs_face_setup && opts.gate && !sessionStorage.getItem('qm_face_skip')) { location.href = '/student/face_setup.html?next=' + encodeURIComponent(location.pathname + location.search); return null; }
    QM_ME = me;
    document.body.innerHTML = `<div class="topbar"><a class="logo" href="/student/dashboard.html">⚡ QuickMark</a>
        <nav class="nav">${STUDENT_NAV.map(n => `<a class="navlink${opts.active === n[0] ? ' active' : ''}" href="${n[2]}">${n[1]}</a>`).join('')}</nav><div class="grow"></div>
        <a class="who" href="/student/profile.html" title="My profile">${avatarHtml(me, 34)}<span class="who-name">${esc(me.name)}</span></a>
        <button id="logout">Logout</button></div>
        <div class="wrap" id="content"><div class="empty">Loading...</div></div>`;
    document.getElementById('logout').onclick = async () => { sessionStorage.removeItem('qm_face_skip'); await api('/api/auth/logout', { method: 'POST' }); location.href = '/student/login.html'; };
    return document.getElementById('content');
}

function toast(message, type) {
    let box = document.querySelector('.toast-box');
    if (!box) { box = document.createElement('div'); box.className = 'toast-box'; document.body.appendChild(box); }
    const t = document.createElement('div'); t.className = 'toast ' + (type || ''); t.textContent = message; box.appendChild(t);
    setTimeout(() => t.remove(), 3500);
}
function onAuthError(e) { if (e.status === 401 || e.status === 403) location.href = '/student/login.html'; else toast(e.message, 'error'); }

// ------------------------------------------------------------------ shared cards
function subjectCard(subjects, threshold) {
    if (!subjects.length) return '<div class="empty">No attendance has been recorded yet.</div>';
    return subjects.map(x => {
        const none = x.percentage === null || x.percentage === undefined;
        return `<div class="subj"><div class="subj-top"><b>${esc(x.subject || x.name)}</b><span class="subtle">${none ? 'No classes yet' : `${x.present} of ${x.total} classes`}</span>
        <span class="pctnum ${none ? '' : x.percentage < threshold ? 'low' : 'ok'}">${none ? '--' : x.percentage + '%'}</span></div>
        <div class="bar"><div class="${none ? '' : x.percentage < threshold ? 'low' : 'ok'}" style="width:${none ? 0 : x.percentage}%"></div></div></div>`;
    }).join('');
}

function historyTable(rows) {
    if (!rows.length) return '<div class="empty">No attendance has been recorded yet.</div>';
    const action = r => r.can_request ? `<button class="btn-mini" data-req="${r.session_id}" data-label="${esc(r.label)}">Request correction</button>`
        : r.request_status === 'pending' ? '<span class="badge waiting">Request pending</span>'
        : r.request_status === 'rejected' ? '<span class="badge absent">Declined</span>' : '';
    return `<div class="tscroll"><table class="htable"><thead><tr><th>Date</th><th>Subject</th><th>Class</th><th>Status</th><th></th></tr></thead><tbody>` +
        rows.map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.subject)}</td><td>${esc(r.label)}</td>
        <td><span class="badge ${r.status === 'present' ? 'done' : 'absent'}">${r.status === 'present' ? 'Present' : 'Absent'}</span></td><td>${action(r)}</td></tr>`).join('') + '</tbody></table></div>';
}

function requestsList(list) {
    if (!list.length) return '<div class="empty">You have not sent any requests.</div>';
    const badge = s => s === 'pending' ? '<span class="badge waiting">Pending</span>' : s === 'approved' ? '<span class="badge done">Approved</span>' : s === 'rejected' ? '<span class="badge absent">Declined</span>' : '<span class="badge">Cancelled</span>';
    return list.map(r => `<div class="session"><div class="info"><div class="t">${esc(r.label)}</div><div class="subtle">${esc(r.date)}${r.message ? ' · “' + esc(r.message) + '”' : ''}</div></div>${badge(r.status)}</div>`).join('');
}

// "My attendance was not marked" (after the session ended). The dialog shows the student's small profile picture,
// the same picture the teacher sees next to the request.
function requestDialog(sessionId, label, onDone) {
    const me = QM_ME || { name: '' };
    const o = document.createElement('div'); o.className = 'overlay';
    o.innerHTML = `<div class="modal"><h3>Request a correction</h3>
        <div class="req-who">${avatarHtml(me, 46)}<div><b>${esc(me.name)}</b><div class="subtle">${esc(me.roll_no ? 'Roll no. ' + me.roll_no : '')}</div></div></div>
        <div class="subtle" style="margin:6px 0 8px">${esc(label)}</div>
        <div class="subtle">Tell your teacher why your attendance was not marked. They will review it and can mark you present.</div>
        <textarea id="rqMsg" maxlength="200" placeholder="Reason (e.g. my phone battery died while I was in class)"></textarea>
        <div id="rqErr" class="error-msg"></div>
        <div class="btn-row"><button class="btn ghost" id="rqCancel">Cancel</button><button class="btn" id="rqSend">Send request</button></div></div>`;
    document.body.appendChild(o); o.querySelector('#rqMsg').focus();
    o.querySelector('#rqCancel').onclick = () => o.remove();
    o.querySelector('#rqSend').onclick = async () => {
        const b = o.querySelector('#rqSend'), err = o.querySelector('#rqErr'); b.disabled = true; err.classList.remove('show');
        try { await api(`/api/student/sessions/${sessionId}/request`, { method: 'POST', body: { message: o.querySelector('#rqMsg').value } }); o.remove(); toast('Request sent to your teacher.', 'success'); if (onDone) onDone(); }
        catch (e) { err.textContent = e.message; err.classList.add('show'); b.disabled = false; }
    };
}
function wireRequestButtons(root, onDone) {
    root.addEventListener('click', e => { const b = e.target.closest('[data-req]'); if (b) requestDialog(b.dataset.req, b.dataset.label, onDone); });
}
