// Forgot password (used by /teacher/forgot.html and /student/forgot.html). Step 1: email -> code. Step 2: code + new password.
const role = document.body.dataset.role;
const $ = id => document.getElementById(id);
const showErr = m => { const e = $('error'); e.textContent = m; e.classList.toggle('show', !!m); };
let email = '';

async function init() {
    let st = { email_enabled: true };
    try { st = await api('/api/auth/forgot-status'); } catch (e) { /* ignore */ }
    if (!st.email_enabled) {
        $('step1').style.display = 'none';
        $('noEmail').style.display = 'block';
        $('noEmail').textContent = role === 'student'
            ? 'Email is not set up on this server, so a code cannot be sent. Please ask your teacher to reset your password (they get a new password for you on the Students page).'
            : 'Email is not set up on this server, so a code cannot be sent. Ask the administrator to set up email (see README), or reset your password from the database.';
    }
}
$('sendBtn').onclick = async () => {
    showErr(''); email = $('email').value.trim();
    if (!email) return showErr('Enter your email address.');
    const b = $('sendBtn'); b.disabled = true; b.textContent = 'Sending...';
    try {
        const r = await api('/api/auth/forgot', { method: 'POST', body: { email, role } });
        $('step1').style.display = 'none'; $('step2').style.display = 'block'; $('sentMsg').textContent = r.message;
    } catch (e) { showErr(e.message); }
    b.disabled = false; b.textContent = 'Send code';
};
$('haveCode').onclick = e => { e.preventDefault(); email = $('email').value.trim(); if (!email) return showErr('Type your email first.'); showErr(''); $('step1').style.display = 'none'; $('step2').style.display = 'block'; $('sentMsg').textContent = ''; };
$('resetBtn').onclick = async () => {
    showErr('');
    if ($('new1').value !== $('new2').value) return showErr('The two passwords do not match.');
    const b = $('resetBtn'); b.disabled = true; b.textContent = 'Saving...';
    try {
        await api('/api/auth/reset-password', { method: 'POST', body: { email, role, code: $('code').value, new_password: $('new1').value } });
        $('step2').style.display = 'none'; $('done').style.display = 'block';
    } catch (e) { showErr(e.message); b.disabled = false; b.textContent = 'Set new password'; }
};
init();
