// Shared UI helpers: toast messages, confirmation dialogs and form modals.

function toast(message, type) {
    let box = document.querySelector('.toast-box');
    if (!box) { box = document.createElement('div'); box.className = 'toast-box'; document.body.appendChild(box); }
    const t = document.createElement('div');
    t.className = 'toast ' + (type || '');
    t.textContent = message;
    box.appendChild(t);
    setTimeout(() => t.remove(), 3500);
}

function _openModal(innerHtml) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' + innerHtml + '</div>';
    document.body.appendChild(overlay);
    return overlay;
}

// Resolves true if the user confirms, false otherwise.
function confirmDialog(message, okText) {
    return new Promise(resolve => {
        const o = _openModal(`<h3>Please confirm</h3><div class="msg">${esc(message)}</div>
            <div class="foot"><button class="btn-ghost" data-r="0">Cancel</button>
            <button class="btn-danger solid" data-r="1">${esc(okText || 'Delete')}</button></div>`);
        o.addEventListener('click', e => {
            const r = e.target.dataset && e.target.dataset.r;
            if (r === undefined && e.target !== o) return;
            o.remove(); resolve(r === '1');
        });
    });
}

// fields: [{name, label, type, value, required, hint, options:[{value,label}], half}]
// onSubmit(values) must return a promise; throw an Error to show its message in the form.
function formDialog(title, fields, onSubmit, saveText) {
    const html = fields.map(f => {
        const input = f.options
            ? `<select name="${f.name}">${f.options.map(o => `<option value="${esc(o.value)}"${String(o.value) === String(f.value) ? ' selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`
            : `<input name="${f.name}" type="${f.type || 'text'}" value="${esc(f.value == null ? '' : f.value)}" autocomplete="off">`;
        return `<div class="field" data-name="${f.name}"><label>${esc(f.label)}${f.required ? ' *' : ''}</label>${input}${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}</div>`;
    }).join('');
    const o = _openModal(`<h3>${esc(title)}</h3><div class="error-msg" id="fdErr"></div>
        <div id="fdFields">${html}</div>
        <div class="foot"><button class="btn-ghost" id="fdCancel">Cancel</button>
        <button class="btn-primary" id="fdSave">${esc(saveText || 'Save')}</button></div>`);
    const first = o.querySelector('input, select'); if (first) first.focus();
    const err = o.querySelector('#fdErr'), save = o.querySelector('#fdSave');
    o.querySelector('#fdCancel').onclick = () => o.remove();
    const submit = async () => {
        const values = {};
        o.querySelectorAll('[name]').forEach(el => values[el.name] = el.value);
        err.classList.remove('show'); save.disabled = true; const old = save.textContent; save.textContent = 'Saving...';
        try { await onSubmit(values); o.remove(); }
        catch (e) { err.textContent = e.message; err.classList.add('show'); save.disabled = false; save.textContent = old; }
    };
    save.onclick = submit;
    o.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') submit(); if (e.key === 'Escape') o.remove(); });
    return o;
}

// Small round picture of a student (their own profile photo, or initials). studentId = the STUDENT's id.
function stuAvatar(studentId, name, hasAvatar, version, size) {
    size = size || 34;
    if (hasAvatar) return `<img class="sav" style="width:${size}px;height:${size}px" src="/api/teacher/students/${studentId}/avatar?v=${encodeURIComponent(version || '')}" alt="${esc(name)}">`;
    const ini = String(name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join('');
    return `<span class="sav sav-init" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.4)}px">${esc(ini)}</span>`;
}
