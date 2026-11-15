// Profile & settings: picture, details, phone, face status, password, downloads.
let content;
const $ = id => document.getElementById(id);

async function render() {
    let p; try { p = await api('/api/student/profile'); } catch (e) { return onAuthError(e); }
    QM_ME = { ...QM_ME, ...p };
    content.innerHTML = `
      ${p.must_change_password ? '<div class="note bad" style="margin-bottom:12px">🔒 Your teacher set your password. You can change it to your own below whenever you like.</div>' : ''}
      <div class="card"><div class="profile-head">${avatarHtml(p, 96)}
        <div><div class="name" style="font-size:22px;font-weight:700">${esc(p.name)}</div><div class="subtle">${p.enrollments.length > 1 ? p.enrollments.length + ' classes' : 'Roll no. ' + esc(p.roll_no)}</div>
          </div></div>
        <div class="note" style="margin-top:12px">${p.has_avatar ? 'Your profile picture is the photo taken during your face setup. It cannot be changed - if it must be redone, ask your teacher to reset your face. Your teacher sees it next to any attendance request you send.' : 'Your profile picture appears automatically from your face setup.'}</div>
        <div id="picMsg"></div></div>
      <div class="card"><h3>My details</h3><div class="kv"><div>Name</div><div>${esc(p.name)}</div><div>Email</div><div>${esc(p.email)}</div></div>
        <h4 style="margin:14px 0 6px">My classes</h4>
        <div class="kv">${p.enrollments.map(e => `<div>${esc(e.class_name)} - ${esc(e.section_name)}</div><div>Roll no. ${esc(e.roll_no)} · ${esc(e.teacher_name)}</div>`).join('')}</div>
        <div class="subtle" style="margin-top:8px">Name, roll number and class are managed by your teacher.</div>
        <div class="field" style="margin-top:14px"><label>Phone number</label><input type="text" id="phone" value="${esc(p.phone)}" maxlength="20"></div>
        <div id="e1" class="error-msg"></div><button class="btn" id="savePhone">Save phone number</button></div>
      <div class="card"><h3>Face check</h3>
        <div class="subtle" style="margin-bottom:10px">${p.face_enrolled ? `✅ Your face is set up${p.face_enrolled_at ? ' (since ' + esc(p.face_enrolled_at.slice(0, 10)) + ')' : ''}. QuickMark keeps 128 numbers that describe it, plus the one small photo from the setup as your profile picture.` : (p.require_face ? '⚠️ Your face is not set up yet. You need it to join sessions.' : 'Your teacher has not turned on face checks. You can still set it up in advance.')}</div>
        ${p.face_enrolled ? '<div class="subtle">If it stops recognising you, ask your teacher to reset it, then set it up again.</div>' : '<a class="btn green" href="/student/face_setup.html?next=/student/profile.html">Set up my face</a>'}</div>
      <div class="card" id="pwCard"><h3>Change password</h3><div id="e2" class="error-msg"></div>
        <div class="field"><label>Current password</label><input type="password" id="cur" autocomplete="current-password"></div>
        <div class="field"><label>New password (at least 6 characters)</label><input type="password" id="new1" autocomplete="new-password"></div>
        <div class="field"><label>Repeat new password</label><input type="password" id="new2" autocomplete="new-password"></div>
        <button class="btn" id="savePw">Change password</button></div>
      <div class="card"><h3>My data</h3><div class="subtle" style="margin-bottom:10px">Download all your attendance as a spreadsheet file.</div>
        <a class="btn ghost" href="/api/student/attendance/export.csv">⬇ Download my attendance (CSV)</a></div>`;

    $('savePhone').onclick = async () => {
        const b = $('savePhone'), er = $('e1'); er.classList.remove('show'); b.disabled = true;
        try { await api('/api/student/profile', { method: 'PUT', body: { phone: $('phone').value } }); toast('Phone number saved.', 'success'); }
        catch (err) { er.textContent = err.message; er.classList.add('show'); } b.disabled = false;
    };
    $('savePw').onclick = async () => {
        const b = $('savePw'), er = $('e2'); er.classList.remove('show'); b.disabled = true;
        try {
            if ($('new1').value !== $('new2').value) throw new Error('The two new passwords do not match.');
            await api('/api/student/password', { method: 'POST', body: { current_password: $('cur').value, new_password: $('new1').value } });
            $('cur').value = $('new1').value = $('new2').value = ''; toast('Password changed.', 'success');
        } catch (err) { er.textContent = err.message; er.classList.add('show'); } b.disabled = false;
    };
}

async function init() {
    content = await initStudent({ active: 'profile', noGate: true }); if (!content) return;
    render();
    if (new URLSearchParams(location.search).get('change')) setTimeout(() => { const c = document.getElementById('pwCard'); if (c) c.scrollIntoView({ behavior: 'smooth' }); }, 200);
}
init();
