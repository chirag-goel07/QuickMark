"""Live updates (Socket.IO) + the background loop that rotates QR tokens every few seconds.

Rooms:  "t<id>" = the teacher watching session <id>   |   "s<id>" = students who joined session <id>
Students never receive the joined/present lists; they only get the session status.
"""
import logging
import time

from flask import session as flask_session
from flask_socketio import emit, join_room

import config
from database.db import _connect, get_db
from extensions import socketio
from services import sessions as svc
from services.qr import qr_svg

log = logging.getLogger("quickmark.realtime")


def teacher_room(sid):
    return f"t{sid}"


def student_room(sid):
    return f"s{sid}"


def push_state(db, session_id, now=None):
    s = svc.get_session(db, session_id)
    if s:
        socketio.emit("state", svc.build_state(db, s, now or time.time()), to=teacher_room(session_id))


def push_status(session_id, status):
    socketio.emit("status", {"status": status}, to=student_room(session_id))


def push_qr(session_id, token):
    socketio.emit("qr", {"token": token, "svg": qr_svg(token),
                         "rotate_seconds": config.ROTATION_SECONDS, "valid_seconds": config.TOKEN_LIFETIME},
                  to=teacher_room(session_id))


def rotation_tick(conn, now):
    """One step of the background loop (also called directly by the tests)."""
    for sid in svc.expire_due_sessions(conn, now):          # time ran out -> save + tell everyone
        push_state(conn, sid, now)
        push_status(sid, "ended")
    for row in conn.execute("SELECT id FROM attendance_sessions WHERE status = 'active'").fetchall():
        push_qr(row["id"], svc.issue_token(conn, row["id"], now))


def rotation_loop(db_path):
    while True:
        began = time.time()
        try:
            conn = _connect(db_path)
            try:
                rotation_tick(conn, time.time())
            finally:
                conn.close()
        except Exception:                                   # keep the loop alive whatever happens
            log.exception("rotation loop error")
        socketio.sleep(max(0.05, config.ROTATION_SECONDS - (time.time() - began)))


def register_socket_handlers():
    @socketio.on("watch")
    def watch(data):
        """The browser asks to receive live updates for one session. We check who is asking first."""
        try:
            sid = int((data or {}).get("session_id"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad session"}
        db, now = get_db(), time.time()
        s = svc.get_session(db, sid)
        role, uid = flask_session.get("role"), flask_session.get("user_id")
        if not s or not uid:
            return {"ok": False, "error": "not allowed"}
        if role == "teacher":
            t = db.execute("SELECT id FROM teachers WHERE user_id = ?", (uid,)).fetchone()
            if not t or t["id"] != s["teacher_id"]:
                return {"ok": False, "error": "not allowed"}
            join_room(teacher_room(sid))
            emit("state", svc.build_state(db, s, now))
            if s["status"] == "active":
                token = svc.latest_token(db, sid, now)
                if token:
                    emit("qr", {"token": token, "svg": qr_svg(token),
                                "rotate_seconds": config.ROTATION_SECONDS, "valid_seconds": config.TOKEN_LIFETIME})
            return {"ok": True}
        if role == "student":
            st = db.execute("SELECT id FROM students WHERE user_id = ?", (uid,)).fetchone()
            if not st or not svc.is_eligible(db, s, st["id"]):
                return {"ok": False, "error": "not allowed"}
            join_room(student_room(sid))
            emit("status", {"status": s["status"]})
            return {"ok": True}
        return {"ok": False, "error": "not allowed"}
