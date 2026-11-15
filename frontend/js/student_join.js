// Join a class with the code the teacher shared. New students create their login here; logged-in students add one more class.
const $ = id => document.getElementById(id);
const showErr = m => { const e = $('error'); e.textContent = m; e.classList.toggle('show', !!m); };
let info = null, code = '', loggedIn = false;

function fmt(v) { v = v.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8); return v.length > 4 ? v.slice(0, 4) + '-' + v.slice(4) : v; }
$('code').addEventListener('input', e => { e.target.value = fmt(e.target.value); });

async function check() {
    showErr(''); code = $('code').value;
    const b = $('checkBtn'); b.disabled = true;
    try {
        info = await api('/api/join/preview', { method: 'POST', body: { code } });
        try { const me = await api('/api/auth/me'); loggedIn = me.role === 'student'; } catch (e) { loggedIn = false; }
        showForm();
    } catch (e) { showErr(e.message); }
    b.disabled = false;
}
function banner() {
    return `<div class="card" style="margin-bottom:12px"><b>${esc(info.class_name)} - ${esc(info.section_name)}</b><div class="subtle">Teacher: ${esc(info.teacher_name)}${info.mode === 'approval' ? ' · your teacher will approve your request' : ''}</div></div>`;
}
function showForm() {
    $('stepCode').style.display = 'none'; const f = $('stepForm'); f.style.display = 'block';
    const next = encodeURIComponent('/student/join.html?code=' + code);
    if (loggedIn) {
        f.innerHTML = banner() + `<div class="field"><label>Your roll number in this section</label><input type="text" id="roll" maxlength="30"></div>
            <button id="goBtn" class="btn full">${info.mode === 'approval' ? 'Ask to join' : 'Join this class'}</button>`;
        $('goBtn').onclick = () => submit('/api/student/join', { code, roll_no: $('roll').value });
    } else {
        f.innerHTML = banner() + `
            <div class="field"><label>Full name</label><input type="text" id="name" maxlength="80" autocomplete="name"></div>
            <div class="field"><label>Roll number</label><input type="text" id="roll" maxlength="30"></div>
            <div class="field"><label>Email (your login)</label><input type="email" id="email" autocomplete="username"></div>
            <div class="field"><label>Phone (optional)</label><input type="text" id="phone" maxlength="20"></div>
            <div class="field"><label>Choose a password</label><input type="password" id="pw" autocomplete="new-password"><div class="hint">At least 6 characters.</div></div>
            <button id="goBtn" class="btn full">${info.mode === 'approval' ? 'Ask to join' : 'Create my account and join'}</button>
            <p class="subtle" style="margin-top:12px">Already have a QuickMark account? <a href="/student/login.html?next=${next}">Log in first</a>, then join.</p>`;
        $('goBtn').onclick = () => submit('/api/join/signup', { code, name: $('name').value, roll_no: $('roll').value, email: $('email').value, phone: $('phone').value, password: $('pw').value });
    }
}
async function submit(url, body) {
    showErr(''); const b = $('goBtn'); b.disabled = true;
    try {
        const r = await api(url, { method: 'POST', body });
        $('stepForm').innerHTML = r.status === 'pending'
            ? `<p>✅ Request sent for <b>${esc(r.where)}</b>.</p><p class="subtle">Your teacher has to approve it. ${loggedIn ? 'You will see a message on your dashboard.' : 'After that, log in with your email and password.'}</p><a class="btn full a-btn" style="text-decoration:none;display:block;text-align:center" href="${loggedIn ? '/student/dashboard.html' : '/student/login.html'}">${loggedIn ? 'Go to dashboard' : 'Go to login'}</a>`
            : `<p>🎉 You joined <b>${esc(r.where)}</b>.</p><a class="btn full a-btn" style="text-decoration:none;display:block;text-align:center" href="/student/dashboard.html">Go to dashboard</a>`;
    } catch (e) { showErr(e.message); b.disabled = false; }
}
$('checkBtn').onclick = check;
document.addEventListener('keydown', e => { if (e.key === 'Enter' && $('stepCode').style.display !== 'none') check(); });
const preset = new URLSearchParams(location.search).get('code');
if (preset) { $('code').value = fmt(preset); check(); }
