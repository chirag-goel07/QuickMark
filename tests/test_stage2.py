"""Stage 2 tests (classes, sections, subjects, students). Run from project root: python tests/test_stage2.py
Uses a temporary database only."""
import os, sys, tempfile, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app

app = create_app(os.path.join(tempfile.mkdtemp(), "t2.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp)
for i, (em, nm) in enumerate([("a@x.com", "Teacher A"), ("b@x.com", "Teacher B")], 1):
    uid = c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?, 'teacher')", (em, generate_password_hash("secret123"))).lastrowid
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (uid, nm))
c.commit(); c.close()

def login(email, role="teacher", password="secret123"):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": password, "role": role}); return cl
A, B, anon = login("a@x.com"), login("b@x.com"), app.test_client()
T = "/api/teacher"

# ---------- auth ----------
check("anonymous blocked from classes (401)", anon.get(f"{T}/classes").status_code == 401)
check("anonymous blocked from students (401)", anon.get(f"{T}/students").status_code == 401)

# ---------- classes ----------
r = A.post(f"{T}/classes", json={"name": "  CSE - 2nd Sem  "}); cid = r.get_json()["id"]
check("add class (201, name trimmed)", r.status_code == 201 and r.get_json()["name"] == "CSE - 2nd Sem")
check("empty class name rejected", A.post(f"{T}/classes", json={"name": "   "}).status_code == 400)
check("101-char class name rejected", A.post(f"{T}/classes", json={"name": "x" * 101}).status_code == 400)
check("duplicate class name rejected (409)", A.post(f"{T}/classes", json={"name": "CSE - 2nd Sem"}).status_code == 409)
check("other teacher CAN reuse the same class name", B.post(f"{T}/classes", json={"name": "CSE - 2nd Sem"}).status_code == 201)
check("edit class", A.put(f"{T}/classes/{cid}", json={"name": "CSE - 3rd Sem"}).get_json()["name"] == "CSE - 3rd Sem")
check("teacher B cannot edit A's class (404)", B.put(f"{T}/classes/{cid}", json={"name": "hack"}).status_code == 404)
check("teacher B cannot delete A's class (404)", B.delete(f"{T}/classes/{cid}").status_code == 404)
check("teacher B list shows only own class", [x["name"] for x in B.get(f"{T}/classes").get_json()["classes"]] == ["CSE - 2nd Sem"])

# ---------- sections / subjects ----------
r = A.post(f"{T}/classes/{cid}/sections", json={"name": "A"}); check("add section A", r.status_code == 201)
A.post(f"{T}/classes/{cid}/sections", json={"name": "B"})
check("duplicate section rejected (409)", A.post(f"{T}/classes/{cid}/sections", json={"name": "A"}).status_code == 409)
check("teacher B cannot add section to A's class (404)", B.post(f"{T}/classes/{cid}/sections", json={"name": "Z"}).status_code == 404)
secs = {s["name"]: s["id"] for s in A.get(f"{T}/classes").get_json()["classes"][0]["sections"]}
check("rename section", A.put(f"{T}/sections/{secs['B']}", json={"name": "C"}).status_code == 200)
r = A.post(f"{T}/classes/{cid}/subjects", json={"name": "DSA"}); check("add subject", r.status_code == 201)
A.post(f"{T}/classes/{cid}/subjects", json={"name": "Digital Logic"})
check("duplicate subject rejected (409)", A.post(f"{T}/classes/{cid}/subjects", json={"name": "DSA"}).status_code == 409)
subs = {s["name"]: s["id"] for s in A.get(f"{T}/classes").get_json()["classes"][0]["subjects"]}
check("rename subject", A.put(f"{T}/subjects/{subs['DSA']}", json={"name": "DSA (C++)"}).status_code == 200)
check("teacher B cannot delete A's subject (404)", B.delete(f"{T}/subjects/{subs['Digital Logic']}").status_code == 404)
check("delete subject", A.delete(f"{T}/subjects/{subs['Digital Logic']}").status_code == 200)

# ---------- students ----------
def stu(**kw):
    d = {"roll_no": "R1", "name": "Amit Kumar", "email": "Amit@College.edu", "phone": "999", "section_id": secs["A"], "password": "pass1234"}
    d.update(kw); return d
r = A.post(f"{T}/students", json=stu()); sid1 = r.get_json()["id"]
check("add student (201, email lowercased)", r.status_code == 201 and r.get_json()["email"] == "amit@college.edu")
check("new student has no percentage yet (None)", r.get_json()["percentage"] is None)
check("duplicate roll number rejected (409)", A.post(f"{T}/students", json=stu(email="o@x.com")).status_code == 409)
check("duplicate email rejected (409)", A.post(f"{T}/students", json=stu(roll_no="R9")).status_code == 409)
check("bad email rejected", A.post(f"{T}/students", json=stu(roll_no="R9", email="notanemail")).status_code == 400)
check("short password rejected", A.post(f"{T}/students", json=stu(roll_no="R9", email="z@x.com", password="123")).status_code == 400)
check("missing name rejected", A.post(f"{T}/students", json=stu(roll_no="R9", email="z@x.com", name="")).status_code == 400)
check("teacher B cannot use A's section (400)", B.post(f"{T}/students", json=stu(roll_no="R9", email="z@x.com")).status_code == 400)
A.post(f"{T}/students", json=stu(roll_no="R2", name="Neha Singh", email="neha@x.com", section_id=secs["B"]))
A.post(f"{T}/students", json=stu(roll_no="R3", name="Rohan Das", email="rohan@x.com"))

# the new student can log in, and is blocked from teacher APIs
sc = login("amit@college.edu", "student", "pass1234")
check("new student can log in with the password the teacher set", sc.get("/api/auth/me").get_json().get("role") == "student")
check("student blocked from student-management API (403)", sc.get(f"{T}/students").status_code == 403)
check("student blocked from class API (403)", sc.post(f"{T}/classes", json={"name": "x"}).status_code == 403)

L = lambda q="": A.get(f"{T}/students{q}").get_json()["students"]
check("list returns 3 students", len(L()) == 3)
check("search by name 'neha'", [s["roll_no"] for s in L("?search=neha")] == ["R2"])
check("search by roll number 'R3'", [s["name"] for s in L("?search=R3")] == ["Rohan Das"])
check("search by email part", len(L("?search=college")) == 1)
check("search wildcard '%' is literal (no match)", L("?search=%25") == [])
check("filter by section", len(L(f"?section_id={secs['A']}")) == 2)
check("filter by class", len(L(f"?class_id={cid}")) == 3)
check("teacher B sees none of A's students", B.get(f"{T}/students").get_json()["students"] == [])
check("teacher B cannot edit A's student (404)", B.put(f"{T}/students/{sid1}", json=stu()).status_code == 404)
check("teacher B cannot delete A's student (404)", B.delete(f"{T}/students/{sid1}").status_code == 404)

# edit
r = A.put(f"{T}/students/{sid1}", json=stu(name="Amit K.", password="", section_id=secs["B"]))
check("edit student: name + section move", r.status_code == 200 and r.get_json()["name"] == "Amit K." and r.get_json()["section_name"] == "C")
check("blank password keeps old password", login("amit@college.edu", "student", "pass1234").get("/api/auth/me").status_code == 200)
A.put(f"{T}/students/{sid1}", json=stu(name="Amit K.", password="newpass99"))
nc = app.test_client(); nc.post("/api/auth/login", json={"email": "amit@college.edu", "password": "newpass99", "role": "student"})
oc = app.test_client(); oc.post("/api/auth/login", json={"email": "amit@college.edu", "password": "pass1234", "role": "student"})
check("  - new password logs in", nc.get("/api/auth/me").status_code == 200)
check("  - old password rejected", oc.get("/api/auth/me").status_code == 401)
check("edit to a roll no used in the SAME section rejected (409)", A.put(f"{T}/students/{sid1}", json=stu(roll_no="R3", password="")).status_code == 409)
check("edit to a roll no used only in ANOTHER section is allowed (200), then back", A.put(f"{T}/students/{sid1}", json=stu(roll_no="R2", password="")).status_code == 200 and A.put(f"{T}/students/{sid1}", json=stu(roll_no="R1", password="")).status_code == 200)

# delete rules
check("cannot delete section that has students (409)", A.delete(f"{T}/sections/{secs['A']}").status_code == 409)
check("cannot delete class that has students (409)", A.delete(f"{T}/classes/{cid}").status_code == 409)

# percentages + low filter: Amit 1/4=25%, Neha 3/4=75%, Rohan 4/4=100%
c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
rows = {s["roll_no"]: s["id"] for s in L()}
pat = {"R1": "aaap", "R2": "pppa", "R3": "pppp"}            # p=present a=absent over 4 sessions
for k in range(4):
    s = c.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,label,status,duration_minutes,total_students) VALUES(1,'normal',?, 'x','ended',10,3)", (secs["A"],)).lastrowid
    for roll, p in pat.items():
        c.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(?,?,?)", (s, rows[roll], "present" if p[k] == "p" else "absent"))
c.commit(); c.close()
pc = {s["roll_no"]: s["percentage"] for s in L()}
check("percentages: R1=25.0 R2=75.0 R3=100.0", pc == {"R1": 25.0, "R2": 75.0, "R3": 100.0})
check("low-only filter returns only R1 (Neha at exactly 75 is not low)", [s["roll_no"] for s in L("?low=1")] == ["R1"])

# deleting a student removes their login + attendance rows
check("delete student", A.delete(f"{T}/students/{rows['R1']}").status_code == 200)
c = sqlite3.connect(dbp)
check("deleted student's records are gone", c.execute("SELECT COUNT(*) FROM attendance_records WHERE student_id=?", (rows["R1"],)).fetchone()[0] == 0)
check("deleted student's login is gone", c.execute("SELECT COUNT(*) FROM users WHERE email='amit@college.edu'").fetchone()[0] == 0)
check("other students' records untouched (8 left)", c.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0] == 8)
c.close()

# empty class can be deleted; sections/subjects go with it
empty = A.post(f"{T}/classes", json={"name": "Empty"}).get_json()["id"]
A.post(f"{T}/classes/{empty}/sections", json={"name": "A"}); A.post(f"{T}/classes/{empty}/subjects", json={"name": "S"})
check("delete empty class", A.delete(f"{T}/classes/{empty}").status_code == 200)
c = sqlite3.connect(dbp)
check("its sections and subjects were removed", c.execute("SELECT COUNT(*) FROM sections WHERE class_id=?", (empty,)).fetchone()[0] == 0
      and c.execute("SELECT COUNT(*) FROM subjects WHERE class_id=?", (empty,)).fetchone()[0] == 0)

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
