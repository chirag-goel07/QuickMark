// Teacher settings: profile, warning threshold, default session duration, password.
let content;
const $ = id => document.getElementById(id);

async function init() {
    content = await initPage('settings', 'Settings', 'Your profile and attendance rules');
    if (!content) return;
    let s; try { s = await api('/api/teacher/settings'); } catch (e) { return handleApiError(e); }
    content.innerHTML = `
      <div class="card center-card"><h3 class="card-title">Profile</h3><div class="error-msg" id="e1"></div>
        <div class="settings-grid">
          <div class="field"><label>Name</label><input type="text" id="name" value="${esc(s.name)}"></div>
          <div class="field"><label>Phone (optional)</label><input type="text" id="phone" value="${esc(s.phone)}"></div>
          <div class="field full"><label>Email (your login)</label><input type="text" value="${esc(s.email)}" readonly></div></div>
        <div style="margin-top:14px"><button class="btn-primary" id="saveProfile">Save</button></div></div>
      <div class="card center-card"><h3 class="card-title">Attendance rules</h3><div class="error-msg" id="e2"></div>
        <div class="settings-grid">
          <div class="field"><label>Attendance warning threshold (%)</label><input type="number" id="threshold" min="1" max="100" step="1" value="${s.warning_threshold}">
            <div class="hint">Students below this appear in the low-attendance lists. Default is 75.</div></div>
          <div class="field"><label>Default session duration (minutes)</label><input type="number" id="minutes" min="1" max="180" step="1" value="${s.session_minutes}">
            <div class="hint">How long the QR stays active unless you change it when starting a session.</div></div>
          <div class="field full"><label style="display:flex;gap:10px;align-items:flex-start;font-size:14px"><input type="checkbox" id="reqFace" style="width:auto;margin-top:3px" ${s.require_face ? 'checked' : ''}>
            <span><b>Require a face scan before students join a session</b><br><span class="hint">Students set up their face once, right after their first login (the server keeps 128 numbers, never a photo), and scan it each time they join. You can reset any student's face on the Students page. A face scan helps stop friends joining for each other but a photo of a face may still fool it, so keep watching the room.</span></span></label></div></div>
        <div style="margin-top:14px"><button class="btn-primary" id="saveRules">Save</button></div></div>
      <div class="card center-card"><h3 class="card-title">Low-attendance alerts</h3><div class="error-msg" id="e4"></div>
        <div class="hint" style="margin-bottom:8px">When a session ends, students who are below ${s.warning_threshold}% always get a message on their dashboard (at most once a week).</div>
        ${s.smtp_configured ? '' : '<div class="warn" style="margin-bottom:10px">Email is not set up on this server, so the two options below cannot send yet (see README, “Email”).</div>'}
        <div class="settings-grid">
          <div class="field full"><label style="display:flex;gap:10px;align-items:flex-start;font-size:14px"><input type="checkbox" id="autoAlerts" style="width:auto;margin-top:3px" ${s.auto_alerts ? 'checked' : ''}><span><b>Also email the student</b><br><span class="hint">An email goes out with the dashboard message.</span></span></label></div>
          <div class="field full"><label style="display:flex;gap:10px;align-items:flex-start;font-size:14px"><input type="checkbox" id="weekly" style="width:auto;margin-top:3px" ${s.weekly_summary ? 'checked' : ''}><span><b>Email me a weekly summary</b><br><span class="hint">Everyone below the threshold, once a week.</span></span></label></div></div>
        <div style="margin-top:14px;display:flex;gap:8px"><button class="btn-primary" id="saveAlerts">Save</button><button class="btn-ghost" id="sendNow">Email me the summary now</button></div></div>
      <div class="card center-card"><h3 class="card-title">Change password</h3><div class="error-msg" id="e3"></div>
        <div class="settings-grid">
          <div class="field full"><label>Current password</label><input type="password" id="cur" autocomplete="current-password"></div>
          <div class="field"><label>New password</label><input type="password" id="new1" autocomplete="new-password"><div class="hint">At least 6 characters.</div></div>
          <div class="field"><label>Repeat new password</label><input type="password" id="new2" autocomplete="new-password"></div></div>
        <div style="margin-top:14px"><button class="btn-primary" id="savePw">Change password</button></div></div>`;

    const save = async (btnId, errId, fn, okMsg) => {
        const b = $(btnId), err = $(errId); err.classList.remove('show'); b.disabled = true;
        try { await fn(); toast(okMsg, 'success'); } catch (e) { err.textContent = e.message; err.classList.add('show'); }
        b.disabled = false;
    };
    const putSettings = () => api('/api/teacher/settings', { method: 'PUT', body: {
        name: $('name').value, phone: $('phone').value, warning_threshold: $('threshold').value, session_minutes: $('minutes').value, require_face: $('reqFace').checked, auto_alerts: $('autoAlerts').checked, weekly_summary: $('weekly').checked } });
    $('saveProfile').onclick = () => save('saveProfile', 'e1', putSettings, 'Profile saved.');
    $('saveRules').onclick = () => save('saveRules', 'e2', putSettings, 'Attendance rules saved.');
    $('saveAlerts').onclick = () => save('saveAlerts', 'e4', putSettings, 'Alert settings saved.');
    $('sendNow').onclick = () => save('sendNow', 'e4', () => api('/api/teacher/settings/send-summary', { method: 'POST' }), 'Summary sent to your email.');
    $('savePw').onclick = () => save('savePw', 'e3', async () => {
        if ($('new1').value !== $('new2').value) throw new Error('The two new passwords do not match.');
        await api('/api/teacher/settings/password', { method: 'POST', body: { current_password: $('cur').value, new_password: $('new1').value } });
        $('cur').value = $('new1').value = $('new2').value = '';
    }, 'Password changed.');
}
init();
