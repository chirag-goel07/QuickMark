"""Stage 6 tests: a student asks for a correction AFTER the session ended.
Run from the project root:  python tests/test_stage6.py   (temporary database only)"""
import os, sys, tempfile, sqlite3, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app
import config

app = create_app(os.path.join(tempfile.mkdtemp(), "t6.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Ms. Sharma"), ("t2@x.com", "Mr. Other")]:
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(2,'ECE')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(2,'A')")
for i, sec in [(1, 1), (2, 1), (3, 1), (4, 1), (5, 2)]:
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}", sec))
def ended_session(days_ago, marks, label):
    end = datetime.now() - timedelta(days=days_ago); start = end - timedelta(minutes=10); f = "%Y-%m-%d %H:%M:%S"
    sid = c.execute("""INSERT INTO attendance_sessions(teacher_id,session_type,section_id,label,status,duration_minutes,total_students,created_at,started_at,ended_at)
                       VALUES(1,'normal',1,?,'ended',10,?,?,?,?)""", (label, len(marks), start.strftime(f), start.strftime(f), end.strftime(f))).lastrowid
    for stu, st in marks.items(): c.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(?,?,?)", (sid, stu, st))
    return sid
P, A = "present", "absent"
recent = ended_session(1, {1: P, 2: A, 3: A, 4: A}, "CSE - A (recent)")        # ended yesterday
old = ended_session(10, {1: P, 2: A, 3: A, 4: A}, "CSE - A (old)")              # ended 10 days ago
edge_ok = ended_session(6.9, {1: P, 2: A, 3: A, 4: A}, "CSE - A (6.9 days)")
edge_no = ended_session(7.1, {1: P, 2: A, 3: A, 4: A}, "CSE - A (7.1 days)")
c.commit(); c.close()
def login(email, role): cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in range(1, 6)}
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))
ST, P_ = "/api/student", "/api/teacher/sessions"
rows = lambda i: {r["session_id"]: r for r in S[i].get(f"{ST}/attendance").get_json()["history"]}

# ---------------------------------------------------------------- what the student sees
h = rows(2)
check("student's history: absent + inside the window -> can_request", h[recent]["can_request"] is True and h[recent]["status"] == "absent" and h[recent]["request_status"] is None)
check("older than 7 days -> can_request False", h[old]["can_request"] is False)
check("boundary: 6.9 days yes, 7.1 days no", h[edge_ok]["can_request"] is True and h[edge_no]["can_request"] is False)
check("a PRESENT row can't be requested", rows(1)[recent]["can_request"] is False)
info = S[2].get(f"{ST}/sessions/{recent}").get_json()
check("session page info: ended, can_request true, status ended", info["status"] == "ended" and info["can_request"] is True and info["my_status"] == "absent")
check("session page info for a present student: can_request false", S[1].get(f"{ST}/sessions/{recent}").get_json()["can_request"] is False)

# ---------------------------------------------------------------- sending the request
R = lambda i, sid, msg=None: S[i].post(f"{ST}/sessions/{sid}/request", json={"message": msg} if msg is not None else {})
check("anonymous 401 / teacher 403", app.test_client().post(f"{ST}/sessions/{recent}/request", json={}).status_code == 401 and T1.post(f"{ST}/sessions/{recent}/request", json={}).status_code == 403)
check("student of ANOTHER teacher cannot ask about this session (403)", R(5, recent).status_code == 403)
check("a present student cannot ask (409)", R(1, recent).status_code == 409)
r = R(2, old, "I was in the lab"); check("session older than the window refused (409) with a clear message", r.status_code == 409 and "7-day" in r.get_json()["error"])
check("7.1 days ago refused (409)", R(2, edge_no).status_code == 409)
check("student 2 asks after the session ended (200)", R(2, recent, "My phone died, I was in class").status_code == 200)
check("the same request twice refused (409)", R(2, recent).status_code == 409)
check("6.9 days ago accepted (200)", R(3, edge_ok, "I was present but could not scan").status_code == 200)
h = rows(2)[recent]; check("student's row now shows request pending and no second button", h["request_status"] == "pending" and h["can_request"] is False)
check("over-long message refused (400)", R(4, recent, "x" * 300).status_code == 400)

# ---------------------------------------------------------------- what the teacher sees
d = T1.get("/api/teacher/dashboard").get_json()
check("dashboard lists both pending requests with session, date and message", sorted((x["name"], x["label"], x["session_status"]) for x in d["requests"]) == [("Student2", "CSE - A (recent)", "ended"), ("Student3", "CSE - A (6.9 days)", "ended")]
      and any(x["message"] == "My phone died, I was in class" for x in d["requests"]) and all(len(x["date"]) == 10 for x in d["requests"]))
check("teacher 2's dashboard shows none of them", T2.get("/api/teacher/dashboard").get_json()["requests"] == [])
hist = {x["id"]: x for x in T1.get("/api/teacher/history").get_json()["sessions"]}
check("history list shows a pending count per session", hist[recent]["pending_requests"] == 1 and hist[edge_ok]["pending_requests"] == 1 and hist[old]["pending_requests"] == 0)
det = T1.get(f"/api/teacher/history/{recent}").get_json()
check("session detail lists the request for the teacher", [r["name"] for r in det["requests"]] == ["Student2"])

# ---------------------------------------------------------------- decisions
rid2 = [x["id"] for x in d["requests"] if x["name"] == "Student2"][0]; rid3 = [x["id"] for x in d["requests"] if x["name"] == "Student3"][0]
check("teacher 2 cannot decide (404), student cannot (403)", T2.post(f"{P_}/requests/{rid2}/accept").status_code == 404 and S[2].post(f"{P_}/requests/{rid2}/accept").status_code == 403)
pct = lambda i: S[i].get(f"{ST}/profile").get_json()["percentage"]
before = pct(2)
check("teacher accepts the late request (200)", T1.post(f"{P_}/requests/{rid2}/accept").status_code == 200)
check("Student2's record flipped absent -> present, marked via 'request'", q("SELECT status, marked_via FROM attendance_records WHERE session_id=? AND student_id=2", recent) == [("present", "request")])
check(f"Student2's percentage rose immediately ({before} -> {pct(2)})", pct(2) > before and pct(2) == 25.0)
check("the session summary followed: 2 present of 4", (lambda j: (j["present"], j["absent"], j["total"]))(T1.get(f"/api/teacher/history/{recent}").get_json()) == (2, 2, 4))
check("audit row logged (absent -> present, kind request)", q("SELECT old_status, new_status, kind FROM attendance_edits WHERE session_id=? AND student_id=2", recent) == [("absent", "present", "request")])
h = rows(2)[recent]; check("student's row: present, request approved, no button", (h["status"], h["request_status"], h["can_request"]) == ("present", "approved", False))
check("accepting twice refused (409)", T1.post(f"{P_}/requests/{rid2}/accept").status_code == 409)
check("the dashboard no longer lists it", [x["name"] for x in T1.get("/api/teacher/dashboard").get_json()["requests"]] == ["Student3"])
check("teacher rejects Student3's request (200)", T1.post(f"{P_}/requests/{rid3}/reject").status_code == 200)
h = rows(3)[edge_ok]; check("Student3: still absent, request rejected, cannot ask again", (h["status"], h["request_status"], h["can_request"]) == ("absent", "rejected", False))
r = R(3, edge_ok); check("asking again after a rejection is refused (409, 'declined')", r.status_code == 409 and "declined" in r.get_json()["error"])
check("dashboard requests list is empty now", T1.get("/api/teacher/dashboard").get_json()["requests"] == [])
check("history pending counts back to 0", all(x["pending_requests"] == 0 for x in T1.get("/api/teacher/history").get_json()["sessions"]))

# ---------------------------------------------------------------- the window is configurable
config.REQUEST_WINDOW_DAYS = 30
check("with a 30-day window the 10-day-old session accepts a request", R(4, old, "late").status_code == 200 and rows(4)[old]["request_status"] == "pending")
config.REQUEST_WINDOW_DAYS = 7
check("window back at 7 days: the other old sessions are closed again", rows(4)[edge_no]["can_request"] is False and R(4, edge_no).status_code == 409)

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
