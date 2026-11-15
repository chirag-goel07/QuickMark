// Low-attendance warning emails.
//   "Email Warning"  -> opens YOUR email app with a ready draft. Nothing is sent by QuickMark.
//   "Send from server" -> QuickMark sends personal emails itself (only if the server has SMTP set up).
function mailtoHref(to, subject, body, bcc) {
    const enc = encodeURIComponent;
    const addr = enc(to || '').replace(/%40/g, '@').replace(/%2C/g, ',');
    let url = 'mailto:' + addr + '?subject=' + enc(subject) + '&body=' + enc(body);
    if (bcc) url += '&bcc=' + enc(bcc.join(',')).replace(/%40/g, '@').replace(/%2C/g, ',');
    return url;
}

// Opens the user's own email app with a draft (kept in one place so it can be replaced in tests).
function openMailto(url) { window.location.href = url; }

// One student: student = {student_id|id, email, subject, body}
async function emailWarning(student) {
    const subject = student.subject || student.warning_subject, body = student.body || student.warning_body;
    openMailto(mailtoHref(student.email, subject, body));
    try { await api('/api/teacher/emails/opened', { method: 'POST', body: { student_ids: [student.student_id || student.id] } }); } catch (e) { /* logging is best effort */ }
    toast('Draft opened in your email app. Review it and press Send there.', 'success');
}

// Everyone below the threshold: two clearly different options.
async function emailAllDialog() {
    let draft, status;
    try { [draft, status] = await Promise.all([api('/api/teacher/emails/bulk-draft'), api('/api/teacher/emails/status')]); }
    catch (e) { return toast(e.message, 'error'); }
    if (!draft.recipients.length) return toast('No students are below the attendance threshold.', 'success');
    const n = draft.recipients.length;
    const o = _openModal(`<h3>Email all low-attendance students (${n})</h3>
        <div class="msg" style="margin-bottom:14px"><b>Option 1 - Open a draft.</b> Opens your email app with all ${n} addresses in BCC (students can't see each other) and a general warning message. <i>Nothing is sent until you press Send in your email app.</i></div>
        <div class="msg"><b>Option 2 - Send from the server.</b> ${status.smtp_configured
            ? `QuickMark sends ${n} <i>personal</i> emails right now (each shows that student's own percentage).`
            : 'Not available: the server has no email account configured (see the README, "Sending real emails").'}</div>
        <div class="foot"><button class="btn-ghost" id="eCancel">Cancel</button>
          <button class="btn-primary" id="eDraft">Open draft</button>
          <button class="btn-danger solid" id="eSend" ${status.smtp_configured ? '' : 'disabled'}>Send ${n} emails now</button></div>`);
    o.querySelector('#eCancel').onclick = () => o.remove();
    o.querySelector('#eDraft').onclick = async () => {
        o.remove();
        openMailto(mailtoHref('', draft.subject, draft.body, draft.recipients));
        toast('Draft opened in your email app. Nothing has been sent yet.', 'success');
    };
    o.querySelector('#eSend').onclick = async () => {
        const b = o.querySelector('#eSend'); b.disabled = true; b.textContent = 'Sending...';
        try {
            const r = await api('/api/teacher/emails/send', { method: 'POST', body: {} });
            o.remove();
            toast(`Sent ${r.sent.length} email(s)` + (r.failed.length ? `, ${r.failed.length} failed (${r.failed.map(f => f.name).join(', ')}).` : '.'), r.failed.length ? 'error' : 'success');
        } catch (e) { b.disabled = false; b.textContent = 'Send emails now'; toast(e.message, 'error'); }
    };
}
