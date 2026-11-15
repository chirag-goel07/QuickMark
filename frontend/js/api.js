// Small helper for talking to the Flask backend. Always sends the login cookie.
async function api(path, options = {}) {
    const opts = { credentials: 'same-origin', headers: {}, ...options };
    if (opts.body && typeof opts.body !== 'string') {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
        const err = new Error(data.error || 'Request failed (' + res.status + ')');
        err.status = res.status;
        err.code = data.code || null;
        throw err;
    }
    return data;
}

// Escape text before putting it in innerHTML (prevents HTML injection from names etc.)
function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
