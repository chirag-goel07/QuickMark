"""Stage 1 tests. Run from the project root:  python tests/test_stage1.py
Uses a throw-away temporary database - your real quickmark.db is never touched."""
import os, sys, tempfile, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app

tmp = tempfile.mkdtemp()
app = create_app(os.path.join(tmp, "test.db"))
db_path = app.config["DATABASE_PATH"]

results = []
def check(name, cond):
    results.append(cond); print(("PASS  " if cond else "FAIL  ") + name)

# ---- build test data directly in the temp DB ----
c = sqlite3.connect(db_path); c.execute("PRAGMA foreign_keys=ON")
def add_user(email, role, pw="secret123"):
    return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash(pw), role)).lastrowid
t_user = add_user("t@x.com", "teacher")
c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (t_user, "Ms. Sharma")); tid = 1
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 2nd Sem')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'B')")
for i, (roll, name) in enumerate([("R1", "Amit"), ("R2", "Neha"), ("R3", "Rohan")], start=1):
    u = add_user(f"s{i}@x.com", "student")
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,1)", (u, roll, name))
# 4 ended sessions. Amit present 2/4 = 50%, Neha 3/4 = 75% (NOT below 75), Rohan 4/4 = 100%
pattern = {1: ["present", "present", "absent", "absent"], 2: ["present"] * 3 + ["absent"], 3: ["present"] * 4}
for n in range(4):
    sid = c.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,label,status,duration_minutes,total_students)"
                    " VALUES(1,'normal',1,'CSE - 2nd Sem A','ended',10,3)").lastrowid
    for stu, st in pattern.items():
        c.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(?,?,?)", (sid, stu, st[n]))
c.commit(); c.close()

cl = app.test_client()

check("dashboard blocked when not logged in (401)", cl.get("/api/teacher/dashboard").status_code == 401)
check("wrong password rejected (401)", cl.post("/api/auth/login", json={"email": "t@x.com", "password": "nope", "role": "teacher"}).status_code == 401)
check("missing fields rejected (400)", cl.post("/api/auth/login", json={"email": "t@x.com"}).status_code == 400)
check("teacher email can't log in as student (401)", cl.post("/api/auth/login", json={"email": "t@x.com", "password": "secret123", "role": "student"}).status_code == 401)

# a student logs in -> must be blocked from the teacher API
sc = app.test_client()
check("student login works", sc.post("/api/auth/login", json={"email": "s1@x.com", "password": "secret123", "role": "student"}).status_code == 200)
check("student blocked from teacher dashboard (403)", sc.get("/api/teacher/dashboard").status_code == 403)

check("teacher login works", cl.post("/api/auth/login", json={"email": "t@x.com", "password": "secret123", "role": "teacher"}).status_code == 200)
d = cl.get("/api/teacher/dashboard").get_json()
check("teacher name returned", d["teacher"]["name"] == "Ms. Sharma")
check("total classes = 1", d["stats"]["total_classes"] == 1)
check("total students = 3", d["stats"]["total_students"] == 3)
check("overall attendance = 9/12 = 75.0", d["stats"]["overall_attendance"] == 75.0)
check("class list has sections A,B", [s["name"] for s in d["classes"][0]["sections"]] == ["A", "B"])
check("low attendance = only Amit (50%); Neha at exactly 75% is not low",
      [(s["name"], s["percentage"]) for s in d["low_attendance"]] == [("Amit", 50.0)])
check("/me returns teacher", cl.get("/api/auth/me").get_json()["role"] == "teacher")
cl.post("/api/auth/logout")
check("after logout dashboard blocked (401)", cl.get("/api/teacher/dashboard").status_code == 401)

# duplicate attendance blocked by database constraint
c = sqlite3.connect(db_path)
try:
    c.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(1,1,'present')"); dup = False
except sqlite3.IntegrityError: dup = True
check("DB rejects duplicate attendance record", dup)
try:
    c.execute("INSERT INTO session_participants(session_id,student_id) VALUES(1,1)")
    c.execute("INSERT INTO session_participants(session_id,student_id) VALUES(1,1)"); dup2 = False
except sqlite3.IntegrityError: dup2 = True
check("DB rejects same student joining a session twice", dup2)

# static pages are served
for p in ["/teacher/login.html", "/teacher/dashboard.html", "/css/teacher.css", "/js/api.js", "/js/dashboard.js"]:
    check(f"serves {p}", cl.get(p).status_code == 200)

# empty-database behaviour: a fresh teacher with no data
e = create_app(os.path.join(tmp, "empty.db")); ec = sqlite3.connect(e.config["DATABASE_PATH"])
u = ec.execute("INSERT INTO users(email,password_hash,role) VALUES('n@x.com',?, 'teacher')", (generate_password_hash("secret123"),)).lastrowid
ec.execute("INSERT INTO teachers(user_id,name) VALUES(?, 'New Teacher')", (u,)); ec.commit(); ec.close()
ecl = e.test_client(); ecl.post("/api/auth/login", json={"email": "n@x.com", "password": "secret123", "role": "teacher"})
ed = ecl.get("/api/teacher/dashboard").get_json()
check("empty DB: zero counts, overall = null, no low list",
      ed["stats"] == {"total_classes": 0, "total_students": 0, "todays_sessions": 0, "overall_attendance": None} and ed["low_attendance"] == [])

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
