// A student's own attendance: overall, subject-wise and the full history (server only returns this student's records).
async function init() {
    const content = await initStudent({ active: 'attendance' }); if (!content) return;
    wireRequestButtons(content, () => init());
    let a, rq; try { [a, rq] = await Promise.all([api('/api/student/attendance'), api('/api/student/requests')]); } catch (e) { return onAuthError(e); }
    const pct = a.percentage === null ? '--' : a.percentage + '%';
    content.innerHTML = `
      <div class="card"><div class="profile"><div><h3 style="margin:0">Overall attendance</h3>
          <div class="subtle">${a.total ? `${a.present} present out of ${a.total} classes` : 'No classes recorded yet'}</div></div>
        <div class="pct"><div class="big ${a.is_low ? 'low' : 'ok'}">${pct}</div><div class="subtle">Required: ${a.threshold}%</div></div></div></div>
      ${a.is_low ? `<div class="warn">⚠️ Your attendance is below the required ${a.threshold}%. Please attend regularly.</div>` : ''}
      <div class="card"><h3>Subject-wise attendance</h3>${subjectCard(a.subjects, a.threshold)}</div>
      <div class="card"><h3>My requests</h3>${requestsList(rq.requests)}<div class="subtle" style="margin-top:8px">Requests are answered by your teacher after the session.</div></div>
      <div class="card"><h3>Attendance history</h3>${historyTable(a.history)}<div class="subtle" style="margin-top:10px">Marked absent by mistake? Use “Request correction” within ${a.request_days} days. Your teacher decides.</div><a class="btn ghost" style="margin-top:12px" href="/api/student/attendance/export.csv">⬇ Download as CSV</a></div>`;
}
init();
