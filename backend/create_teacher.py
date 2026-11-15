"""Create a teacher account.
Usage:  python create_teacher.py "Ms. Sharma" sharma@college.edu
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from database.db import _connect, init_db
from werkzeug.security import generate_password_hash

if len(sys.argv) != 3:
    sys.exit('Usage: python create_teacher.py "Teacher Name" email@example.com')

name, email = sys.argv[1], sys.argv[2].strip().lower()
password = getpass.getpass("Password (min 6 chars): ")
if len(password) < 6:
    sys.exit("Password too short.")

init_db(config.DATABASE_PATH)
conn = _connect(config.DATABASE_PATH)
try:
    cur = conn.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'teacher')",
                       (email, generate_password_hash(password)))
    conn.execute("INSERT INTO teachers (user_id, name, warning_threshold, session_minutes, require_face) VALUES (?, ?, ?, ?, 1)",
                 (cur.lastrowid, name, config.DEFAULT_WARNING_THRESHOLD, config.DEFAULT_SESSION_MINUTES))
    conn.commit()
    print(f"Teacher '{name}' created.")
    if not os.environ.get("QUICKMARK_LAUNCHER"):                    # start.py does the next steps itself
        print("Next: python make_cert.py (once, for the camera), then python app.py, then open the teacher login page it prints.")
except Exception as e:
    sys.exit(f"Could not create teacher: {e}")
