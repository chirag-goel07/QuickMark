import time

from flask import Blueprint, jsonify, request

from database.db import get_db
from middleware.auth import current_teacher, login_required
from services import realtime
from services import sessions as svc

bp = Blueprint("sessions", __name__, url_prefix="/api/teacher/sessions")


def _error(e):
    return jsonify(error=e.message, code=e.code), e.status


def _own(db, teacher, session_id):
    s = svc.get_session(db, session_id)
    if not s or s["teacher_id"] != teacher["id"]:
        raise svc.SessionError("Session not found.", 404)
    return s


@bp.get("/current")
@login_required("teacher")
def current():
    """The teacher's unfinished session (so a page refresh can resume it) + default duration."""
    db, t, now = get_db(), current_teacher(), time.time()
    svc.expire_due_sessions(db, now)
    s = svc.open_session_for_teacher(db, t["id"])
    return jsonify(session=None if not s else {"id": s["id"], "label": s["label"], "status": s["status"], "type": s["session_type"]},
                   default_duration=t["session_minutes"])


@bp.post("")
@login_required("teacher")
def create():
    db, t, now = get_db(), current_teacher(), time.time()
    data = request.get_json(silent=True) or {}
    try:
        svc.expire_due_sessions(db, now)
        kind = data.get("type", "normal")
        if kind == "normal":
            sid = svc.create_normal_session(db, t, data.get("section_id"), data.get("subject_id") or None,
                                            data.get("duration_minutes"), now)
        elif kind == "group":
            sid = svc.create_group_session(db, t, data.get("group_id"), data.get("duration_minutes"), now)
        else:
            raise svc.SessionError("Unknown session type.", 400)
    except svc.SessionError as e:
        return _error(e)
    return jsonify(id=sid), 201


@bp.get("/<int:session_id>")
@login_required("teacher")
def state(session_id):
    db, t, now = get_db(), current_teacher(), time.time()
    try:
        svc.expire_due_sessions(db, now)
        s = _own(db, t, session_id)
    except svc.SessionError as e:
        return _error(e)
    return jsonify(svc.build_state(db, s, now))


@bp.post("/<int:session_id>/start")
@login_required("teacher")
def start(session_id):
    """The ONLY place the first QR token is created - the QR stays hidden until the teacher presses this."""
    db, t, now = get_db(), current_teacher(), time.time()
    try:
        _own(db, t, session_id)
        token = svc.start_session(db, session_id, now)
    except svc.SessionError as e:
        return _error(e)
    realtime.push_state(db, session_id, now)
    realtime.push_qr(session_id, token)
    realtime.push_status(session_id, "active")
    return jsonify(ok=True)


@bp.post("/<int:session_id>/end")
@login_required("teacher")
def end(session_id):
    db, t, now = get_db(), current_teacher(), time.time()
    try:
        s = _own(db, t, session_id)
        if s["status"] != "active":
            raise svc.SessionError("Only a running session can be ended.", 409)
        svc.finalize_session(db, session_id, now)
    except svc.SessionError as e:
        return _error(e)
    realtime.push_state(db, session_id, now)
    realtime.push_status(session_id, "ended")
    return jsonify(svc.build_state(db, svc.get_session(db, session_id), now))


@bp.post("/<int:session_id>/cancel")
@login_required("teacher")
def cancel(session_id):
    db, t = get_db(), current_teacher()
    try:
        _own(db, t, session_id)
        svc.cancel_waiting_session(db, session_id)
    except svc.SessionError as e:
        return _error(e)
    realtime.push_status(session_id, "cancelled")
    return jsonify(ok=True)


@bp.post("/<int:session_id>/mark")
@login_required("teacher")
def mark(session_id):
    """Attendance cannot be edited while the session is running. Editing is done after it ends (Attendance History -> Edit)."""
    db, t = get_db(), current_teacher()
    try:
        _own(db, t, session_id)
    except svc.SessionError as e:
        return _error(e)
    return jsonify(error="Attendance can only be edited after the session has ended."), 409


def _decide(request_id, accept):
    db, t, now = get_db(), current_teacher(), time.time()
    try:
        s = svc.resolve_request(db, t["id"], request_id, accept, now)
    except svc.SessionError as e:
        return _error(e)
    realtime.push_state(db, s["id"], now)
    realtime.push_status(s["id"], s["status"])          # the student's page reloads and shows the decision
    return jsonify(ok=True, session_id=s["id"], status="approved" if accept else "rejected")


@bp.post("/requests/<int:request_id>/accept")
@login_required("teacher")
def accept_request(request_id):
    return _decide(request_id, True)


@bp.post("/requests/<int:request_id>/reject")
@login_required("teacher")
def reject_request(request_id):
    return _decide(request_id, False)
