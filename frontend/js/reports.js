// Reports: overall numbers, class/section charts, trend, student-wise table, low-attendance list.
let content, data, charts = [], sortKey = 'percentage', sortDir = 1;
const COLORS = { ok: '#1A5FE0', low: '#D92D2D' };

const pill = (p, thr) => p === null ? '<span class="pill none">--</span>' : `<span class="pill ${p < thr ? '' : 'ok'}">${p}%</span>`;

function makeChart(id, type, labels, values, label) {
    const ctx = document.getElementById(id); if (!ctx) return;
    const thr = data.threshold;
    charts.push(new Chart(ctx, {
        type, data: { labels, datasets: [{ label, data: values, borderColor: '#1A5FE0', tension: .25, fill: false,
            backgroundColor: type === 'bar' ? values.map(v => v !== null && v < thr ? COLORS.low : COLORS.ok) : '#1A5FE0' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
            scales: { y: { min: 0, max: 100, title: { display: true, text: 'Attendance %' } } } } }));
}

function studentsTable() {
    const list = [...data.students].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey];
        if (av === null && bv === null) return 0; if (av === null) return 1; if (bv === null) return -1;
        return (typeof av === 'string' ? av.localeCompare(bv) : av - bv) * sortDir;
    });
    const th = (key, label) => `<th class="sort-th" data-sort="${key}">${label}${sortKey === key ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}</th>`;
    document.getElementById('stuTable').innerHTML = list.length ? `<table class="data"><thead><tr>${th('roll_no', 'Roll No')}${th('name', 'Name')}${th('class_name', 'Class')}${th('section_name', 'Section')}${th('present', 'Present')}${th('total', 'Sessions')}${th('percentage', 'Attendance')}</tr></thead><tbody>` +
        list.map(s => `<tr><td>${esc(s.roll_no)}</td><td><b>${esc(s.name)}</b></td><td>${esc(s.class_name)}</td><td>${esc(s.section_name)}</td><td>${s.present}</td><td>${s.total}</td><td>${pill(s.percentage, data.threshold)}</td></tr>`).join('') + '</tbody></table>'
        : '<div class="empty">No students yet.</div>';
}

function render() {
    const o = data.overall;
    const low = data.low_students;
    content.innerHTML = `
      <div class="tiles">
        <div class="tile orange"><div class="num">${o.percentage === null ? '--' : o.percentage + '%'}</div><div class="lbl">Overall attendance</div></div>
        <div class="tile blue"><div class="num">${o.sessions}</div><div class="lbl">Finished sessions</div></div>
        <div class="tile green"><div class="num">${o.students}</div><div class="lbl">Students · ${o.classes} classes</div></div>
        <div class="tile purple"><div class="num">${o.low}</div><div class="lbl">Below ${data.threshold}%</div></div></div>
      ${o.sessions === 0 ? '<div class="card"><div class="empty">No attendance has been completed yet, so there is nothing to chart. Take attendance and press End Attendance.</div></div>' : `
      <div class="chart-grid">
        <div class="card"><div class="card-head"><h3 class="card-title">Class-wise attendance</h3><div class="grow"></div><a class="btn-ghost btn-sm a-btn" href="/api/teacher/reports/export.csv?kind=classes">⬇ CSV</a></div><div class="chart-box"><canvas id="cClass"></canvas></div></div>
        <div class="card"><div class="card-head"><h3 class="card-title">Section-wise attendance</h3><div class="grow"></div><a class="btn-ghost btn-sm a-btn" href="/api/teacher/reports/export.csv?kind=sections">⬇ CSV</a></div><div class="chart-box"><canvas id="cSec"></canvas></div></div>
        <div class="card wide"><div class="card-head"><h3 class="card-title">Attendance trend (by day)</h3></div><div class="chart-box"><canvas id="cTrend"></canvas></div></div>
      </div>`}
      <div class="card"><div class="card-head"><h3 class="card-title">❗ Low-attendance students (below ${data.threshold}%)</h3><div class="grow"></div>
          ${low.length ? '<button class="btn-primary btn-sm" id="repEmailAll">✉ Email All</button>' : ''}
          <a class="btn-ghost btn-sm a-btn" href="/api/teacher/reports/export.csv?kind=low">⬇ CSV</a></div>
        ${low.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Roll No</th><th>Name</th><th>Class</th><th>Attendance</th><th></th></tr></thead><tbody>${
            low.map((s, i) => `<tr><td>${esc(s.roll_no)}</td><td><b>${esc(s.name)}</b></td><td>${esc(s.class_name)} - ${esc(s.section_name)}</td><td>${pill(s.percentage, data.threshold)}</td>
            <td class="actions"><button class="btn-ghost btn-sm" data-low="${i}">✉ Email Warning</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Nobody is below the threshold.</div>'}</div>
      <div class="card"><div class="card-head"><h3 class="card-title">Student-wise attendance</h3><div class="grow"></div><a class="btn-ghost btn-sm a-btn" href="/api/teacher/reports/export.xlsx">⬇ Excel (sheet per section)</a><a class="btn-ghost btn-sm a-btn" href="/api/teacher/reports/export.csv?kind=students">⬇ CSV</a></div>
        <div class="table-wrap" id="stuTable"></div></div>`;
    studentsTable();
    if (o.sessions) {
        const cl = data.classes.filter(c => c.percentage !== null), se = data.sections.filter(s => s.percentage !== null);
        makeChart('cClass', 'bar', cl.map(c => c.name), cl.map(c => c.percentage), 'Attendance %');
        makeChart('cSec', 'bar', se.map(s => s.class_name + ' ' + s.section_name), se.map(s => s.percentage), 'Attendance %');
        makeChart('cTrend', 'line', data.trend.map(t => t.day), data.trend.map(t => t.percentage), 'Attendance %');
    }
}

async function init() {
    content = await initPage('reports', 'Reports', 'Attendance statistics from the database');
    if (!content) return;
    try { data = await api('/api/teacher/reports'); } catch (e) { return handleApiError(e); }
    render();
    content.addEventListener('click', e => {
        const th = e.target.closest('[data-sort]');
        if (th) { sortDir = sortKey === th.dataset.sort ? -sortDir : 1; sortKey = th.dataset.sort; return studentsTable(); }
        if (e.target.id === 'repEmailAll') return emailAllDialog();
        const b = e.target.closest('[data-low]');
        if (b) { const s = data.low_students[Number(b.dataset.low)]; emailWarningById(s); }
    });
}

// the report rows don't carry the email text, so fetch the ready-made warning from the dashboard data
async function emailWarningById(s) {
    try {
        const d = await api('/api/teacher/dashboard');
        const full = d.low_attendance.find(x => x.student_id === s.id);
        if (!full) return toast('This student is no longer below the threshold.', 'error');
        emailWarning(full);
    } catch (e) { toast(e.message, 'error'); }
}
init();
