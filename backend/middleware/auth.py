from functools import wraps

from flask import jsonify, session

from database.db import get_db


def login_required(role):
    """Protect an API route. role is 'teacher' or 'student'.
    The user id always comes from the server-side session, never from the browser request."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return jsonify(error="Please log in first."), 401
            if session.get("role") != role:
                return jsonify(error="You do not have permission for this action."), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_teacher():
    return get_db().execute(
        "SELECT * FROM teachers WHERE user_id = ?", (session["user_id"],)
    ).fetchone()
