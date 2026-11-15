"""Stage 3b tests: groups + group attendance (same waiting-room flow as normal attendance).
Run from the project root:  python tests/test_stage3b.py   (temporary database only)"""
import os, sys, tempfile, sqlite3, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app
from extensions import socketio
from services import sessions as svc

app = create_app(os.path.join(tempfile.mkdtemp(), "t3b.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp)
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Teacher One"), ("t2@x.com", "Teacher Two")]:
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 2nd Sem')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(2,'ECE')")
for n in "AB": c.execute("INSERT INTO sections(class_id,name) VALUES(1,?)", (n,))
c.execute("INSERT INTO sections(class_id,name) VALUES(2,'A')")
# students 1,2 in section A; 3,4 in section B (teacher 1);  5 belongs to teacher 2
for i, sec in [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3)]:
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}", sec))
c.commit(); c.close()
def login(email, role):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in range(1, 6)}
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))
G, P = "/api/teacher/groups", "/api/teacher/sessions"

# ---------------- groups CRUD
check("student cannot use groups API (403)", S[1].get(G).status_code == 403)
check("anonymous cannot use groups API (401)", app.test_client().get(G).status_code == 401)
check("group name required (400)", T1.post(G, json={"name": " ", "student_ids": [1]}).status_code == 400)
check("student_ids must be a list (400)", T1.post(G, json={"name": "X", "student_ids": "1,2"}).status_code == 400)
check("garbage ids rejected (400)", T1.post(G, json={"name": "X", "student_ids": ["a"]}).status_code == 400)
check("cannot add another teacher's student (400)", T1.post(G, json={"name": "X", "student_ids": [1, 5]}).status_code == 400)
check("nonexistent student id rejected (400)", T1.post(G, json={"name": "X", "student_ids": [999]}).status_code == 400)
r = T1.post(G, json={"name": "Project Team", "student_ids": [1, 3, 3]}); gid = r.get_json()["id"]
check("create group across sections (201), duplicate ids collapsed", r.status_code == 201 and r.get_json()["member_count"] == 2)
check("members show class + section", {(m["name"], m["section_name"]) for m in r.get_json()["members"]} == {("Student1", "A"), ("Student3", "B")})
check("duplicate group name rejected (409)", T1.post(G, json={"name": "Project Team", "student_ids": [2]}).status_code == 409)
check("other teacher may reuse the name", T2.post(G, json={"name": "Project Team", "student_ids": [5]}).status_code == 201)
check("list shows only own groups with counts", [(g["name"], g["member_count"]) for g in T1.get(G).get_json()["groups"]] == [("Project Team", 2)])
check("teacher 2 cannot read teacher 1's group (404)", T2.get(f"{G}/{gid}").status_code == 404)
check("teacher 2 cannot edit it (404)", T2.put(f"{G}/{gid}", json={"name": "h", "student_ids": []}).status_code == 404)
check("teacher 2 cannot delete it (404)", T2.delete(f"{G}/{gid}").status_code == 404)
r = T1.put(f"{G}/{gid}", json={"name": "Lab Team", "student_ids": [1, 2, 4]})
check("edit: rename + replace members", r.status_code == 200 and r.get_json()["name"] == "Lab Team" and {m["id"] for m in r.get_json()["members"]} == {1, 2, 4})
check("empty group can be saved but not started", T1.post(G, json={"name": "Empty", "student_ids": []}).status_code == 201)
eid = [g["id"] for g in T1.get(G).get_json()["groups"] if g["name"] == "Empty"][0]
check("starting a session for an empty group refused (400)", T1.post(P, json={"type": "group", "group_id": eid}).status_code == 400)
check("starting a session for another teacher's group refused (400)", T1.post(P, json={"type": "group", "group_id": 2}).status_code == 400)
check("unknown session type refused (400)", T1.post(P, json={"type": "weird"}).status_code == 400)

# ---------------- full group attendance flow over the real API
r = T1.post(P, json={"type": "group", "group_id": gid, "duration_minutes": 10}); sid = r.get_json()["id"]
check("group session created (201)", r.status_code == 201)
st = T1.get(f"{P}/{sid}").get_json()
check("waiting room: label 'Group: Lab Team', total 3, type group", st["label"] == "Group: Lab Team" and st["total"] == 3 and st["type"] == "group" and st["status"] == "waiting")
check("NO QR token exists in the group waiting room", q("SELECT COUNT(*) FROM qr_tokens")[0][0] == 0)
check("group is locked: cannot edit while its session is open (409)", T1.put(f"{G}/{gid}", json={"name": "x", "student_ids": [1]}).status_code == 409)
check("group is locked: cannot delete while its session is open (409)", T1.delete(f"{G}/{gid}").status_code == 409)
check("GET group shows locked=true", T1.get(f"{G}/{gid}").get_json()["locked"] is True)
check("group list also reports locked=true", [g["locked"] for g in T1.get(G).get_json()["groups"] if g["id"] == gid] == [True])
check("a normal session cannot be opened at the same time (409)", T1.post(P, json={"type": "normal", "section_id": 1}).status_code == 409)

ids = lambda i: [x["id"] for x in S[i].get("/api/student/sessions/active").get_json()["sessions"]]
check("members (S1 sec A, S4 sec B) see the session; non-member S3 and other-teacher S5 do not",
      ids(1) == [sid] and ids(4) == [sid] and ids(3) == [] and ids(5) == [])
check("non-member cannot join (403)", S[3].post(f"/api/student/sessions/{sid}/join").status_code == 403)
check("student of another teacher cannot join (403)", S[5].post(f"/api/student/sessions/{sid}/join").status_code == 403)
tsock = socketio.test_client(app, flask_test_client=T1); tsock.emit("watch", {"session_id": sid}, callback=True); tsock.get_received()
check("non-member cannot watch the session room", socketio.test_client(app, flask_test_client=S[3]).emit("watch", {"session_id": sid}, callback=True)["ok"] is False)
check("member from section A joins", S[1].post(f"/api/student/sessions/{sid}/join").status_code == 200)
S[4].post(f"/api/student/sessions/{sid}/join")
ev = [e for e in tsock.get_received() if e["name"] == "state"]
check("teacher gets live joins: 2 of 3 = 67%", ev and ev[-1]["args"][0]["joined"] == 2 and ev[-1]["args"][0]["joined_pct"] == 67)
check("joining twice is not counted twice", S[1].post(f"/api/student/sessions/{sid}/join").get_json()["already_joined"] is True and T1.get(f"{P}/{sid}").get_json()["joined"] == 2)
check("student 2 (member, not yet joined) is counted in the total only", T1.get(f"{P}/{sid}").get_json()["total"] == 3)

tsock.get_received()
check("teacher starts group attendance", T1.post(f"{P}/{sid}/start").status_code == 200)
qr = [e for e in tsock.get_received() if e["name"] == "qr"]
check("QR pushed to the teacher only after start", len(qr) == 1)
tok = qr[0]["args"][0]["token"]
scan = lambda i, t: S[i].post("/api/student/attendance/scan", json={"token": t})
check("member S1 scans -> present", scan(1, tok).status_code == 200)
check("duplicate scan rejected (409)", scan(1, tok).status_code == 409)
check("non-member S3 cannot mark attendance (403)", scan(3, tok).status_code == 403)
check("member S2 who never joined cannot mark attendance (403)", scan(2, tok).status_code == 403)
check("member from the other section S4 scans -> present", scan(4, tok).status_code == 200)
check("student of another teacher cannot mark attendance (403)", scan(5, tok).status_code == 403)
r = T1.post(f"{P}/{sid}/end").get_json()
check("end: present 2, absent 1 (S2), total 3", (r["present"], r["absent"], r["total"]) == (2, 1, 3) and [x["name"] for x in r["absent_students"]] == ["Student2"])
check("records only exist for the 3 members", sorted(x[0] for x in q("SELECT student_id FROM attendance_records WHERE session_id=?", sid)) == [1, 2, 4])
check("group unlocked after the session ends", T1.get(f"{G}/{gid}").get_json()["locked"] is False)

# group sessions feed the same percentages as normal sessions
check("group attendance counts toward student %: S1=100%, S2=0% (low)",
      S[1].get("/api/student/profile").get_json()["percentage"] == 100.0 and S[2].get("/api/student/profile").get_json()["percentage"] == 0.0)
d = T1.get("/api/teacher/dashboard").get_json()
check("dashboard lists today's group session as ended with 3 students",
      [(g["label"], g["status"], g["total_students"]) for g in d["todays_groups"]] == [("Group: Lab Team", "ended", 3)])
check("dashboard low list has Student2 (0%)", ("Student2", 0.0) in [(x["name"], x["percentage"]) for x in d["low_attendance"]])

# ---------------- cancelling, then editing/deleting the group works again
sid2 = T1.post(P, json={"type": "group", "group_id": gid}).get_json()["id"]
check("cancel a waiting group session", T1.post(f"{P}/{sid2}/cancel").status_code == 200)
r = T1.put(f"{G}/{gid}", json={"name": "Lab Team", "student_ids": [1, 2]})
check("group editable again after cancel", r.status_code == 200 and r.get_json()["member_count"] == 2)
check("delete group (200)", T1.delete(f"{G}/{gid}").status_code == 200)
check("members removed with the group", q("SELECT COUNT(*) FROM group_members WHERE group_id=?", gid)[0][0] == 0)
check("past session keeps its record and label", q("SELECT label, status FROM attendance_sessions WHERE id=?", sid)[0] == ("Group: Lab Team", "ended")
      and q("SELECT COUNT(*) FROM attendance_records WHERE session_id=?", sid)[0][0] == 3)
check("deleting a student removes them from their groups",
      (lambda: (T1.post(G, json={"name": "G2", "student_ids": [1, 2]}), T1.delete("/api/teacher/students/2"))[1].status_code == 200
       and q("SELECT COUNT(*) FROM group_members WHERE student_id=2")[0][0] == 0)())

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
