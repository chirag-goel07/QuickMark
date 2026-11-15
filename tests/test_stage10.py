"""Stage 10 tests: teacher's student-details window (profile, class attendance) used from the group editor,
and groups built from whole sections. Run from the project root:  python tests/test_stage10.py   (temporary database only)"""
import os, sys, tempfile, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app

app = create_app(os.path.join(tempfile.mkdtemp(), "t10.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Teacher One"), ("t2@x.com", "Teacher Two")]:
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'ML')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'ML1')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'ML2')")
c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'Maths')")
for i, sec in [(1, 1), (2, 1), (3, 2)]:
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}", sec))
# two ended sessions: student 1 present then absent
c.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,subject_id,label,status,duration_minutes,started_at,ended_at,total_students) VALUES(1,'normal',1,1,'ML - ML1','ended',10,'2026-11-01 10:00:00','2026-11-01 10:10:00',2)")
c.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,subject_id,label,status,duration_minutes,started_at,ended_at,total_students) VALUES(1,'normal',1,1,'ML - ML1','ended',10,'2026-11-02 10:00:00','2026-11-02 10:10:00',2)")
for sid, stu, st in [(1, 1, "present"), (1, 2, "absent"), (2, 1, "absent"), (2, 2, "absent")]:
    c.execute("INSERT INTO attendance_records(session_id,student_id,status,marked_at,marked_via) VALUES(?,?,?,?,?)", (sid, stu, st, "2026-11-01 10:01:00", "qr"))
c.commit(); c.close()

def login(email, role):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2, S1 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher"), login("s1@x.com", "student")
A = "/api/teacher"

r = T1.get(f"{A}/students/1/details"); d = r.get_json()
check("teacher gets the details of their own student", r.status_code == 200 and d["student"]["name"] == "Student1" and d["student"]["section_name"] == "ML1" and d["student"]["class_name"] == "ML")
check("details hold no face data or password", "face_descriptor" not in str(d) and "password" not in str(d))
check("overall attendance: 1 present of 2 = 50%, low, with advice", d["overall"]["percentage"] == 50.0 and d["overall"]["present"] == 1 and d["overall"]["absent"] == 1
      and d["overall"]["total"] == 2 and d["overall"]["is_low"] and d["overall"]["advice"]["status"] == "below" and d["overall"]["advice"]["classes_needed"] == 2)
check("subject-wise rows and recent sessions are included (newest first)", d["subjects"] == [{"subject": "Maths", "present": 1, "total": 2, "percentage": 50.0}]
      and [h["date"] for h in d["history"]] == ["2026-11-02", "2026-11-01"] and d["history"][1]["status"] == "present")
check("student with no records: no percentage, empty lists", T1.get(f"{A}/students/3/details").get_json()["overall"]["percentage"] is None
      and T1.get(f"{A}/students/3/details").get_json()["history"] == [])
check("another teacher cannot see them (404)", T2.get(f"{A}/students/1/details").status_code == 404)
check("a student cannot use it (403) / anonymous (401)", S1.get(f"{A}/students/1/details").status_code == 403 and app.test_client().get(f"{A}/students/1/details").status_code == 401)
check("unknown student (404)", T1.get(f"{A}/students/999/details").status_code == 404)

# a group made from ONE ticked section = exactly that section's students
r = T1.post(f"{A}/groups", json={"name": "ML1 only", "student_ids": [1, 2]})
check("group of section ML1 created with its 2 unique students", r.status_code == 201 and r.get_json()["member_count"] == 2 and {m["section_name"] for m in r.get_json()["members"]} == {"ML1"})
sec = {s["name"]: s for s in T1.get(f"{A}/classes").get_json()["classes"][0]["sections"]}
check("class list gives every section with its student count (used for the section tick-boxes)", sec["ML1"]["student_count"] == 2 and sec["ML2"]["student_count"] == 1)
check("students list gives each student's section_id (used to show one section at a time)",
      {s["id"]: s["section_id"] for s in T1.get(f"{A}/students").get_json()["students"]} == {1: sec["ML1"]["id"], 2: sec["ML1"]["id"], 3: sec["ML2"]["id"]})

# ---- groups made of sections (the teacher ticks sections; no student list involved)
sid = {n: v["id"] for n, v in sec.items()}
r = T1.post(f"{A}/groups", json={"name": "By section", "section_ids": [sid["ML1"]]}); g = r.get_json()
check("group from the ticked section ML1: its 2 students, one section, marked as section group",
      r.status_code == 201 and g["member_count"] == 2 and g["by_sections"] and [x["name"] for x in g["sections"]] == ["ML1"] and g["sections"][0]["student_count"] == 2)
r = T1.post(f"{A}/groups", json={"name": "Two sections", "section_ids": [sid["ML1"], sid["ML2"]]})
check("two sections = all 3 students", r.status_code == 201 and r.get_json()["member_count"] == 3)
check("no section ticked is refused", T1.post(f"{A}/groups", json={"name": "Empty", "section_ids": []}).status_code == 400)
check("another teacher's section is refused", T2.post(f"{A}/groups", json={"name": "Steal", "section_ids": [sid["ML1"]]}).status_code == 400)
check("garbage section ids are refused", T1.post(f"{A}/groups", json={"name": "Bad", "section_ids": ["x"]}).status_code == 400)
# a student joins ML1 later: the group follows the section
T1.post(f"{A}/students", json={"roll_no": "R9", "name": "Newcomer", "email": "new@x.com", "section_id": sid["ML1"]})
listed = {x["name"]: x for x in T1.get(f"{A}/groups").get_json()["groups"]}
check("a student added to the section later is in the group automatically", listed["By section"]["member_count"] == 3 and listed["Two sections"]["member_count"] == 4)
check("group list tells each group's sections", [x["name"] for x in listed["Two sections"]["sections"]] == ["ML1", "ML2"])
r = T1.put(f"{A}/groups/{g['id']}", json={"name": "By section", "section_ids": [sid["ML2"]]})
check("editing: group now follows ML2 only", r.status_code == 200 and r.get_json()["member_count"] == 1 and r.get_json()["sections"][0]["name"] == "ML2")
r = T1.post(f"{A}/groups", json={"name": "Legacy", "student_ids": [1]}); lg = r.get_json()
check("old way (picked students) still works and is marked as such", r.status_code == 201 and lg["member_count"] == 1 and lg["by_sections"] is False and lg["sections"][0]["name"] == "ML1")
# natural roll order inside a section: R1, R2, R9, R10 (plain text order would give R1, R10, R2, R9)
T1.post(f"{A}/students", json={"roll_no": "R10", "name": "Tenth", "email": "ten@x.com", "section_id": sid["ML1"]})
students = T1.get(f"{A}/students").get_json()["students"]
ml1 = [x["roll_no"] for x in students if x["section_name"] == "ML1"]
check("students list: section by section, rolls in natural order", ml1 == ["R1", "R2", "R9", "R10"] and [x["section_name"] for x in students] == sorted(x["section_name"] for x in students))
# a section group can really be started; it counts the students who joined after it was saved
r = T1.post("/api/teacher/sessions", json={"type": "group", "group_id": listed["Two sections"]["id"]})
c2 = sqlite3.connect(dbp); row = c2.execute("SELECT total_students, label FROM attendance_sessions WHERE id = ?", (r.get_json().get("session_id") or r.get_json().get("id"),)).fetchone(); c2.close()
check("starting the section group counts all 5 students currently in ML1 + ML2", r.status_code in (200, 201) and row and row[0] == 5)

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
