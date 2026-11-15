import os


def _env(name, default=""):
    """Settings come from QUICKMARK_<NAME>. The old ATTENDSURE_<NAME> names still work so existing setups keep running."""
    return os.environ.get("QUICKMARK_" + name, os.environ.get("ATTENDSURE_" + name, default))


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

_db_dir = os.path.join(BASE_DIR, "database")
_old_db = os.path.join(_db_dir, "attendsure.db")
_new_db = os.path.join(_db_dir, "quickmark.db")
DATABASE_PATH = _env("DB", _old_db if (os.path.exists(_old_db) and not os.path.exists(_new_db)) else _new_db)
def _load_secret_key():
    """Login cookies are signed with this key. Each installation creates its OWN random key the first time
    it runs (saved in backend/secret.key so logins survive a restart). Or set the SECRET_KEY environment variable."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(BASE_DIR, "secret.key")
    try:
        with open(path) as f:
            key = f.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    import secrets
    key = secrets.token_hex(32)
    try:
        with open(path, "w") as f:
            f.write(key)
    except OSError:
        pass                                   # read-only folder: fall back to a key for this run only
    return key


SECRET_KEY = _load_secret_key()

DEFAULT_WARNING_THRESHOLD = 75      # percent
DEFAULT_SESSION_MINUTES = 10

# QR rotation: the teacher screen shows a NEW server-made token every ROTATION_SECONDS.
# A token is accepted for TOKEN_LIFETIME seconds (rotation + a little time for scanning/network),
# so at most two tokens are valid at the same moment.
ROTATION_SECONDS = float(_env("ROTATION", 3))
TOKEN_LIFETIME = float(_env("TOKEN_LIFETIME", 5))

# ---- Optional: sending real emails from the SERVER (never put these in frontend code) ----
# Leave SMTP_HOST empty to disable sending; the "Email Warning" buttons still open a pre-filled draft.
# Example (Gmail needs an "app password"):  set QUICKMARK_SMTP_HOST=smtp.gmail.com  QUICKMARK_SMTP_PORT=587
#   QUICKMARK_SMTP_USER=you@gmail.com  QUICKMARK_SMTP_PASSWORD=app-password  QUICKMARK_SMTP_TLS=starttls
SMTP_HOST = _env("SMTP_HOST", "")
SMTP_PORT = int(_env("SMTP_PORT", 587))
SMTP_USER = _env("SMTP_USER", "")
SMTP_PASSWORD = _env("SMTP_PASSWORD", "")
SMTP_FROM = _env("SMTP_FROM", "") or SMTP_USER
SMTP_TLS = _env("SMTP_TLS", "starttls")      # starttls | ssl | none

# ---- Face verification (students scan their face before joining a session) ----
# Distance between the live face and the enrolled face; SMALLER = more alike. 0.5 is stricter than face-api's usual 0.6.
FACE_MATCH_THRESHOLD = float(_env("FACE_THRESHOLD", 0.5))
FACE_MAX_FAILS = 5            # wrong-face attempts allowed ...
FACE_FAIL_WINDOW = 60         # ... per this many seconds, then the student must wait

# A student marked absent can ask the teacher for a correction for this many days after the session ended.
REQUEST_WINDOW_DAYS = int(_env("REQUEST_DAYS", 7))

# Students send "please mark me present" requests AFTER a session has ended (see REQUEST_WINDOW_DAYS).
# Set QUICKMARK_REQUESTS_DURING_SESSION=1 if you also want to allow them while the session is still running.
REQUESTS_DURING_SESSION = _env("REQUESTS_DURING_SESSION", "0") == "1"
