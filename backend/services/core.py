"""Python side of the C++ core (backend/cpp).

The OOP / DSA logic of QuickMark lives in C++ (rate limiter, face maths + lock-out, attendance statistics,
natural / stable sorting, CSV safety). This file only converts Python values to plain C values and back (ctypes),
so Flask, the database and the HTML/CSS/JS stay exactly as they were.
"""
import ctypes
import math
import os
import sys
import threading

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
import build_cpp  # noqa: E402

_lock = threading.Lock()


def _load():
    """1) shipped prebuilt library, 2) one you built, 3) compile now. Explains in plain words if none works."""
    with _lock:
        problems = []
        for path in build_cpp.candidates():
            try:
                return ctypes.CDLL(path), path
            except OSError as e:
                problems.append(f"could not load {os.path.relpath(path, _BACKEND)}: {e}")
        try:
            path = build_cpp.build()                            # no usable library: compile it now (needs a C++ compiler)
            return ctypes.CDLL(path), path
        except Exception as e:                                  # noqa: BLE001 - turn anything into one readable message
            problems.append(str(e).strip().splitlines()[0] if str(e).strip() else repr(e))
        raise RuntimeError(
            "The QuickMark C++ core could not be loaded.\n"
            f"  This computer: {build_cpp.system_tag()}, Python {build_cpp.python_bits()}-bit\n"
            + "".join(f"  - {p}\n" for p in problems) +
            "\nWhat to do:\n"
            "  * Windows: install 64-bit Python from python.org (a 32-bit Python cannot load the ready-made library), then run start.bat again.\n"
            "  * Or install a C++ compiler once (Windows: MSYS2 / MinGW-w64 g++ or Visual Studio Build Tools; Mac: xcode-select --install;\n"
            "    Linux: sudo apt install build-essential), then run:  python build_cpp.py")


_lib, LIBRARY_PATH = _load()
_D, _I, _LL, _C = ctypes.c_double, ctypes.c_int, ctypes.c_longlong, ctypes.c_char_p
_DP = ctypes.POINTER(_D)


def _sig(name, res, *args):
    f = getattr(_lib, name)
    f.restype, f.argtypes = res, list(args)
    return f


_version = _sig("qm_version", _C)
_rl_allow = _sig("qm_rl_allow", _I, _C, _I, _D, _D)
_rl_reset = _sig("qm_rl_reset", None)
_rl_keys = _sig("qm_rl_keys", _I)
_face_validate = _sig("qm_face_validate", _I, _DP, _I)
_face_distance = _sig("qm_face_distance", _D, _DP, _DP, _I)
_face_enroll = _sig("qm_face_enroll", _I, _DP, _I, _I, _D, _DP)
_lock_check = _sig("qm_lock_check", _I, _LL, _D, _D, _I)
_lock_fail = _sig("qm_lock_fail", None, _LL, _D)
_lock_clear = _sig("qm_lock_clear", None, _LL)
_lock_count = _sig("qm_lock_count", _I, _LL)
_lock_reset_all = _sig("qm_lock_reset_all", None)
_lock_seed = _sig("qm_lock_seed", None, _LL, _D, _I)
_percent = _sig("qm_percent", _I, _LL, _LL, _DP)
_advice = _sig("qm_advice", _I, _LL, _LL, _LL, ctypes.POINTER(_LL))
_order_ascending = _sig("qm_order_ascending", None, _DP, _I, ctypes.POINTER(_I))
_natural_order = _sig("qm_natural_order", None, ctypes.POINTER(_C), _I, ctypes.POINTER(_I))
_streak = _sig("qm_streak", _I, ctypes.POINTER(_I), _I)
_csv_sanitize = _sig("qm_csv_sanitize", _I, _C, ctypes.c_char_p, _I)
_csv_new = _sig("qm_csv_new", ctypes.c_void_p)
_csv_add_row = _sig("qm_csv_add_row", None, ctypes.c_void_p, ctypes.POINTER(_C), ctypes.POINTER(_I), _I)
_csv_data = _sig("qm_csv_data", ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_I))
_csv_free = _sig("qm_csv_free", None, ctypes.c_void_p)


def _utf8(text):
    return str(text).encode("utf-8", "replace")


def version():
    return _version().decode()


# ---------------------------------------------------------------- rate limiter
def rate_allow(key, limit, window_seconds, now):
    return bool(_rl_allow(_utf8(key), int(limit), float(window_seconds), float(now)))


def rate_reset():
    _rl_reset()


# ---------------------------------------------------------------- face
def face_is_valid(vec):
    """128 finite numbers, each within -5..5."""
    arr = (_D * len(vec))(*vec)
    return bool(_face_validate(arr, len(vec)))


def face_distance(a, b):
    n = min(len(a), len(b))
    return _face_distance((_D * n)(*a[:n]), (_D * n)(*b[:n]), n)


def face_enroll(samples, consistency):
    """(True, average) if all captures look like one face, else (False, None)."""
    count, dim = len(samples), len(samples[0])
    flat = (_D * (count * dim))(*[x for s in samples for x in s])
    out = (_D * dim)()
    ok = _face_enroll(flat, count, dim, float(consistency), out)
    return (True, list(out)) if ok == 1 else (False, None)


def lockout_is_locked(student_id, now, window, max_fails):
    return bool(_lock_check(int(student_id), float(now), float(window), int(max_fails)))


def lockout_fail(student_id, now):
    _lock_fail(int(student_id), float(now))


def lockout_clear(student_id):
    _lock_clear(int(student_id))


def lockout_count(student_id):
    return _lock_count(int(student_id))


def lockout_reset_all():
    _lock_reset_all()


def lockout_seed(student_id, when, times):
    _lock_seed(int(student_id), float(when), int(times))


# ---------------------------------------------------------------- statistics
def percent(present, total):
    """Attendance % with 1 decimal, or None when there is nothing recorded."""
    out = _D()
    return out.value if _percent(int(present), int(total), ctypes.byref(out)) else None


def advice(present, total, threshold):
    """None | {"status": "ok", "can_miss": n} | {"status": "below", "classes_needed": n or None}"""
    n = _LL()
    kind = _advice(int(present), int(total), int(threshold), ctypes.byref(n))
    if kind == 0:
        return None
    if kind == 1:
        return {"status": "ok", "can_miss": n.value}
    return {"status": "below", "classes_needed": n.value if kind == 2 else None}


def sorted_by_value(items, key):
    """items sorted by key(item) ascending (stable, numbers only)."""
    items = list(items)
    if len(items) < 2:
        return items
    vals = (_D * len(items))(*[key(x) for x in items])
    idx = (_I * len(items))()
    _order_ascending(vals, len(items), idx)
    return [items[i] for i in idx]


def natural_sorted(items, key=lambda x: x):
    """items in natural order of key(item) (a string): 2 before 10, A9 before A10, any case."""
    items = list(items)
    if len(items) < 2:
        return items
    arr = (_C * len(items))(*[_utf8(key(x)) for x in items])
    idx = (_I * len(items))()
    _natural_order(arr, len(items), idx)
    return [items[i] for i in idx]


def leading_streak(flags):
    """How many True values at the start of the list."""
    arr = (_I * len(flags))(*[1 if f else 0 for f in flags])
    return _streak(arr, len(flags))


# ---------------------------------------------------------------- CSV
def csv_safe(cell):
    """A text cell that would be run as a formula by Excel gets a leading apostrophe; None becomes ''."""
    if isinstance(cell, str):
        raw = _utf8(cell)
        buf = ctypes.create_string_buffer(len(raw) + 4)
        _csv_sanitize(raw, buf, len(buf))
        return buf.value.decode("utf-8", "replace")
    return "" if cell is None else cell


def csv_text(headers, rows):
    """The whole CSV as text (with a BOM so Excel shows non-English names correctly)."""
    handle = _csv_new()
    try:
        for r in [list(headers)] + [list(x) for x in rows]:
            cells = (_C * len(r))(*[_utf8("" if c is None else c) for c in r])
            flags = (_I * len(r))(*[1 if isinstance(c, str) else 0 for c in r])
            _csv_add_row(handle, cells, flags, len(r))
        n = _I()
        ptr = _csv_data(handle, ctypes.byref(n))
        return ctypes.string_at(ptr, n.value).decode("utf-8", "replace")
    finally:
        _csv_free(handle)
