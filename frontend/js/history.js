// Attendance history: finished sessions, filters, per-session detail, CSV export.
let content, classes = [], rows = [];
const f = { class_id: '', type: '', from: '', to: '' };

const pctPill = (p, threshold) => p === null ? '<span class="pill none">--</span>' : `<span class="pill ${p >= (threshold || 75) ? 'ok' : ''}">${p}%</span>`;
function query() {
    const q = new URLSearchParams();
    if (f.class_id) q.set('class_id', f.class_id); if (f.type) q.set('type', f.type);
    if (f.from) q.set('from', f.from); if (f.to) q.set('to', f.to);
    return q.toString() ? '?' + q : '';
}

function renderShell() {
    content.innerHTML = `
      <div class="card"><div class="toolbar">
        <div class="field"><label>Class</label><select id="hClass"><option value="">All classes</option>${classes.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Type</label><select id="hType"><option value="">Section + Group</option><option value="normal">Section only</option><option value="group">Group only</option></select></div>
        <div class="field"><label>From</label><input type="date" id="hFrom"></div>
        <div class="field"><label>To</label><input type="date" id="hTo"></div>
        <button class="btn-ghost" id="hClear">Clear</button><div class="grow"></div>
        <a class="btn-primary a-btn" id="hCsv" href="#">⬇ Export CSV</a></div></div>
      <div class="card"><div class="table-wrap" id="hTable"><div class="loading">Loading...</div></div></div>`;
}

async function load() {
    try { rows = (await api('/api/teacher/history' + query())).sessions; } catch (e) { return handleApiError(e); }
    document.getElementById('hCsv').href = '/api/teacher/history/export.csv' + query();
    const box = document.getElementById('hTable');
    if (!rows.length) { box.innerHTML = '<div class="empty">No finished attendance sessions match. Sessions appear here after you press End Attendance.</div>'; return; }
    box.innerHTML = `<table class="data"><thead><tr><th>Date</th><th>Class / Group</th><th>Subject</th><th>Total</th><th>Present</th><th>Absent</th><th>Attendance</th><th></th></tr></thead><tbody>` +
        rows.map(r => `<tr data-id="${r.id}"><td>${esc(r.date)}</td><td><b>${esc(r.label)}</b></td><td>${esc(r.subject || '-')}</td>
          <td>${r.total}</td><td>${r.present}</td><td>${r.absent}</td><td>${pctPill(r.percentage)}${r.pending_requests ? ` <span class="pill mid" title="Requests waiting">✉ ${r.pending_requests}</span>` : ''}</td>
          <td class="actions"><button class="btn-ghost btn-sm" data-act="view">View</button></td></tr>`).join('') +
        `</tbody></table><div class="subtle" style="margin-top:10px">${rows.length} session${rows.length === 1 ? '' : 's'}</div>`;
}

const VIA_TXT = { teacher: 'edited by you', request: 'request approved', qr: '' };

async function showDetail(id) {
    let d; try { d = await api('/api/teacher/history/' + id); } catch (e) { return toast(e.message, 'error'); }
    const old = document.querySelector('.overlay'); if (old) old.remove();
    const o = _openModal(`<h3>${esc(d.label)}</h3>
        <div class="subtle" style="margin-bottom:12px">${esc(d.date)} · started ${esc((d.started_at || '').slice(11, 16))} · ended ${esc((d.ended_at || '').slice(11, 16))}</div>
        <div class="tiles"><div class="tile blue"><div class="num">${d.total}</div><div class="lbl">Total</div></div>
          <div class="tile green"><div class="num">${d.present}</div><div class="lbl">Present</div></div>
          <div class="tile orange"><div class="num">${d.absent}</div><div class="lbl">Absent</div></div></div>
        <div class="progress green" style="margin-top:14px"><div style="width:${d.percentage || 0}%"></div></div><div class="subtle">${d.percentage === null ? '' : d.percentage + '% attendance'}</div>
        ${d.requests.length ? `<div class="chips-label">Requests waiting for you</div>${d.requests.map(r => `<div class="req-row">${stuAvatar(r.student_id, r.name, r.has_avatar, r.avatar_v, 44)}<div class="req-info"><b>${esc(r.name)}</b> <span class="subtle">${esc(r.roll_no)}</span>${r.message ? `<div class="req-msg">“${esc(r.message)}”</div>` : ''}</div>
            <button class="btn-primary btn-sm" data-ra="${r.id}">Accept</button><button class="btn-danger btn-sm" data-rr="${r.id}">Reject</button></div>`).join('')}` : ''}
        <div class="chips-label">Edit attendance <span class="subtle">(one box per section · every change is logged)</span></div>
        ${d.sections.map(sec => `<div class="card sec-box" style="margin:10px 0;padding:12px"><div class="session-top" style="margin-bottom:8px"><h4 style="margin:0">${esc(sec.label)}</h4>
          <span class="subtle">${sec.present} present · ${sec.absent} absent</span></div>
          <div class="edit-list">${sec.students.map(p => `<div class="edit-row ${p.status}"><span style="display:flex;align-items:center;gap:8px">${stuAvatar(p.id, p.name, p.has_avatar, p.avatar_v, 28)}<span><b>${esc(p.name)}</b> <span class="subtle">${esc(p.roll_no)}</span>${VIA_TXT[p.via] ? ` <i class="subtle">· ${VIA_TXT[p.via]}</i>` : ''}</span></span>
            <span class="pill ${p.status === 'present' ? 'ok' : ''}">${p.status === 'present' ? 'Present' : 'Absent'}</span>
            <button class="btn-ghost btn-sm" data-set="${p.id}" data-to="${p.status === 'present' ? 'absent' : 'present'}">Mark ${p.status === 'present' ? 'absent' : 'present'}</button></div>`).join('')}</div></div>`).join('')}
        <div class="foot"><a class="btn-ghost a-btn" style="padding:10px 16px" href="/api/teacher/history/${id}.csv">⬇ CSV</a><a class="btn-ghost a-btn" style="padding:10px 16px" href="/api/teacher/history/${id}.xlsx">⬇ Excel</a><button class="btn-primary" id="dClose">Close</button></div>`);
    o.querySelector('.modal').classList.add('wide');
    o.querySelector('#dClose').onclick = () => { o.remove(); load(); };
    o.addEventListener('click', async e => {
        const set = e.target.closest('[data-set]'), ra = e.target.closest('[data-ra]'), rr = e.target.closest('[data-rr]');
        try {
            if (set) { set.disabled = true; await api(`/api/teacher/history/${id}/records`, { method: 'PUT', body: { student_id: Number(set.dataset.set), status: set.dataset.to } }); toast('Attendance updated.', 'success'); }
            else if (ra || rr) { const b = ra || rr; b.disabled = true; await api(`/api/teacher/sessions/requests/${ra ? ra.dataset.ra : rr.dataset.rr}/${ra ? 'accept' : 'reject'}`, { method: 'POST' }); toast(ra ? 'Accepted. The student is now present.' : 'Request rejected.', 'success'); }
            else return;
            showDetail(id);
        } catch (err) { toast(err.message, 'error'); }
    });
}

function wireFilters() {
    [['hClass', 'class_id'], ['hType', 'type'], ['hFrom', 'from'], ['hTo', 'to']].forEach(([id, key]) => {
        const el = document.getElementById(id);
        el.value = f[key];
        el.addEventListener('change', e => { f[key] = e.target.value; load(); });
    });
    document.getElementById('hClear').onclick = () => { Object.keys(f).forEach(k => f[k] = ''); renderShell(); wireFilters(); load(); };
}

async function init() {
    content = await initPage('history', 'Attendance History', 'Every finished attendance session');
    if (!content) return;
    try { classes = (await api('/api/teacher/classes')).classes; } catch (e) { return handleApiError(e); }
    renderShell(); wireFilters(); load();
    const open = new URLSearchParams(location.search).get('open'); if (open) showDetail(open);
    content.addEventListener('click', e => { const b = e.target.closest('[data-act=view]'); if (b) showDetail(b.closest('tr').dataset.id); });
}
init();
