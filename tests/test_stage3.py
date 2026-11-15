"""Stage 3 tests: sessions, waiting room, live updates, rotating QR, scanning, duplicates, expiry.
Run from the project root:  python tests/test_stage3.py      (temporary database only)"""
import os, sys, tempfile, sqlite3, threading, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app
from extensions import socketio
from services import realtime, sessions as svc
import config

app = create_app(os.path.join(tempfile.mkdtemp(), "t3.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

# ------------------------------------------------------------ test data
c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Teacher One"), ("t2@x.com", "Teacher Two")]:
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 2nd Sem')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'B')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'C')")
c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'DSA')")
for i, sec in [(1, 1), (2, 1), (3, 1), (4, 2)]:
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}", sec))
c.commit(); c.close()

def login(email, role):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in (1, 2, 3, 4)}
def q(sql, *a):
    cc = sqlite3.connect(dbp); r = cc.execute(sql, a).fetchall(); cc.close(); return r
P = "/api/teacher/sessions"

# ------------------------------------------------------------ create
check("student cannot create a session (403)", S[1].post(P, json={"section_id": 1}).status_code == 403)
check("anonymous cannot create a session (401)", app.test_client().post(P, json={"section_id": 1}).status_code == 401)
check("section with no students rejected (400)", T1.post(P, json={"section_id": 3}).status_code == 400)
check("teacher 2 cannot use teacher 1's section (400)", T2.post(P, json={"section_id": 1}).status_code == 400)
check("bad duration rejected (400)", T1.post(P, json={"section_id": 1, "duration_minutes": 0}).status_code == 400)
r = T1.post(P, json={"section_id": 1, "subject_id": 1, "duration_minutes": 10}); sid = r.get_json()["id"]
check("create session (201)", r.status_code == 201)
check("second open session refused (409)", T1.post(P, json={"section_id": 2}).status_code == 409)
check("/current resumes the open session", T1.get(f"{P}/current").get_json()["session"]["id"] == sid)
st = T1.get(f"{P}/{sid}").get_json()
check("waiting state: label, total=3, joined=0, 0%", st["label"] == "CSE - 2nd Sem - A (DSA)" and st["status"] == "waiting" and st["total"] == 3 and st["joined"] == 0 and st["joined_pct"] == 0)
check("teacher 2 cannot read teacher 1's session (404)", T2.get(f"{P}/{sid}").status_code == 404)
check("student cannot read teacher session API (403)", S[1].get(f"{P}/{sid}").status_code == 403)

# ------------------------------------------------------------ QR hidden in the waiting room
check("NO QR token exists while waiting", q("SELECT COUNT(*) FROM qr_tokens")[0][0] == 0)
check("scan with a guessed token fails while waiting (400)", S[1].post("/api/student/attendance/scan", json={"token": "abc"}).status_code == 400)

# ------------------------------------------------------------ live waiting room via sockets
tsock = socketio.test_client(app, flask_test_client=T1)
check("teacher socket can watch own session", tsock.emit("watch", {"session_id": sid}, callback=True)["ok"])
tsock.get_received()
check("teacher 2 cannot watch teacher 1's session", socketio.test_client(app, flask_test_client=T2).emit("watch", {"session_id": sid}, callback=True)["ok"] is False)
check("section-B student cannot watch the session", socketio.test_client(app, flask_test_client=S[4]).emit("watch", {"session_id": sid}, callback=True)["ok"] is False)
ssock = socketio.test_client(app, flask_test_client=S[1]); check("eligible student can watch status", ssock.emit("watch", {"session_id": sid}, callback=True)["ok"])
ssock.get_received()

check("student sees the open session in their list", [x["id"] for x in S[1].get("/api/student/sessions/active").get_json()["sessions"]] == [sid])
check("section-B student does NOT see it", S[4].get("/api/student/sessions/active").get_json()["sessions"] == [])
check("section-B student cannot join (403)", S[4].post(f"/api/student/sessions/{sid}/join").status_code == 403)

r = S[1].post(f"/api/student/sessions/{sid}/join"); check("student 1 joins", r.status_code == 200 and r.get_json()["already_joined"] is False)
ev = [e for e in tsock.get_received() if e["name"] == "state"]
check("teacher receives a LIVE state push when a student joins", ev and ev[-1]["args"][0]["joined"] == 1 and ev[-1]["args"][0]["joined_pct"] == 33)
r = S[1].post(f"/api/student/sessions/{sid}/join"); check("joining twice is harmless and not counted twice", r.get_json()["already_joined"] is True and T1.get(f"{P}/{sid}").get_json()["joined"] == 1)
S[2].post(f"/api/student/sessions/{sid}/join")
st = T1.get(f"{P}/{sid}").get_json()
check("2 of 3 joined = 67%, names listed", st["joined"] == 2 and st["joined_pct"] == 67 and {x["name"] for x in st["joined_students"]} == {"Student1", "Student2"})
check("student 3 has NOT joined", all(x["id"] != 3 for x in st["joined_students"]))
check("student cannot see other students' names from their own API", "joined_students" not in S[1].get(f"/api/student/sessions/{sid}").get_json())
check("student room gets no 'state' push (only status)", all(e["name"] != "state" for e in ssock.get_received()))

# ------------------------------------------------------------ start -> QR appears
check("student cannot start the session (403)", S[1].post(f"{P}/{sid}/start").status_code == 403)
check("teacher 2 cannot start it (404)", T2.post(f"{P}/{sid}/start").status_code == 404)
tsock.get_received(); ssock.get_received()
check("teacher starts attendance (200)", T1.post(f"{P}/{sid}/start").status_code == 200)
ev = tsock.get_received(); names = [e["name"] for e in ev]
check("teacher receives 'qr' (svg + token) and 'state'=active after start", "qr" in names and "state" in names
      and [e for e in ev if e["name"] == "state"][-1]["args"][0]["status"] == "active")
qrev = [e for e in ev if e["name"] == "qr"][-1]["args"][0]
check("QR payload: <svg> markup, token, rotate=3s", qrev["svg"].lstrip().startswith("<svg") and len(qrev["token"]) >= 12 and qrev["rotate_seconds"] == 3)
check("students are told the session is now active", any(e["name"] == "status" and e["args"][0]["status"] == "active" for e in ssock.get_received()))
check("starting twice is refused (409)", T1.post(f"{P}/{sid}/start").status_code == 409)
tok = qrev["token"]

# ------------------------------------------------------------ scanning rules
scan = lambda i, t: S[i].post("/api/student/attendance/scan", json={"token": t})
check("valid scan by joined student 1 -> present", scan(1, tok).status_code == 200)
r = scan(1, tok); check("duplicate scan rejected (409)", r.status_code == 409 and "already marked" in r.get_json()["error"])
check("fake token rejected (400)", scan(2, "not-a-real-token").status_code == 400)
check("student 3 (never joined) cannot mark attendance (403)", scan(3, tok).status_code == 403)
check("section-B student 4 cannot mark attendance (403)", scan(4, tok).status_code == 403)
check("scan with no token field rejected (400)", S[2].post("/api/student/attendance/scan", json={}).status_code == 400)
check("teacher cannot use the student scan API (403)", T1.post("/api/student/attendance/scan", json={"token": tok}).status_code == 403)
ev = [e for e in tsock.get_received() if e["name"] == "state"]
check("teacher gets a live push after the scan: present=1", ev and ev[-1]["args"][0]["present"] == 1 and ev[-1]["args"][0]["present_students"][0]["name"] == "Student1")
check("student 1 sees their own marked status", S[1].get(f"/api/student/sessions/{sid}").get_json()["my_status"] == "present")

# ------------------------------------------------------------ rotation + expiry of QR tokens
cc = sqlite3.connect(dbp); cc.row_factory = sqlite3.Row
now = time.time()
t_a = svc.issue_token(cc, sid, now); t_b = svc.issue_token(cc, sid, now + 3); t_c = svc.issue_token(cc, sid, now + 6)
check("every rotation produces a different token", len({t_a, t_b, t_c, tok}) == 4)
def accepts(token, at):   # server-side check with a controlled clock (DB left untouched)
    row = cc.execute("SELECT expires_at FROM qr_tokens WHERE token=?", (token,)).fetchone(); return bool(row) and row["expires_at"] >= at
check("token valid 4s after it was made", accepts(t_a, now + 4))
check("token INVALID 5.5s after it was made (expired)", not accepts(t_a, now + 5.5))
check("at 6.5s the current token t_c is valid, the 2-rotations-old t_a is not", accepts(t_c, now + 6.5) and not accepts(t_a, now + 6.5))
cc.execute("UPDATE qr_tokens SET expires_at = ? WHERE token = ?", (time.time() - 1, t_a)); cc.commit()
r = scan(2, t_a); check("EXPIRED token rejected by the server (400)", r.status_code == 400 and "expired" in r.get_json()["error"])
check("student 2 NOT marked after expired scan", q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND student_id=2", sid)[0][0] == 0)
check("a fresh token still works (student 2)", scan(2, t_c).status_code == 200)

# the background tick: creates a new token and pushes it to the teacher
tsock.get_received()
before = q("SELECT COUNT(*) FROM qr_tokens WHERE session_id=?", sid)[0][0]
realtime.rotation_tick(cc, time.time())
pushed = [e for e in tsock.get_received() if e["name"] == "qr"]
check("rotation tick pushes a NEW qr to the teacher screen", len(pushed) == 1 and pushed[0]["args"][0]["token"] not in {tok, t_a, t_b, t_c})
check("rotation tick stored the new token in the DB", q("SELECT COUNT(*) FROM qr_tokens WHERE session_id=?", sid)[0][0] == before + 1)

# ------------------------------------------------------------ concurrency: 15 simultaneous scans by ONE student
cur_tok = svc.issue_token(cc, sid, time.time())
# student 3 joins, then 15 threads scan together
S[3].post(f"/api/student/sessions/{sid}/join")
out = []
clients = [login("s3@x.com", "student") for _ in range(15)]
def hit2(cl): out.append(cl.post("/api/student/attendance/scan", json={"token": cur_tok}).status_code)
th = [threading.Thread(target=hit2, args=(cl,)) for cl in clients]; [t.start() for t in th]; [t.join() for t in th]
check("15 simultaneous scans by one student -> exactly 1 success, 14 duplicates", sorted(out).count(200) == 1 and sorted(out).count(409) == 14)
check("exactly one attendance row for that student", q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND student_id=3", sid)[0][0] == 1)

# ------------------------------------------------------------ end
check("student cannot end the session (403)", S[1].post(f"{P}/{sid}/end").status_code == 403)
check("teacher 2 cannot end it (404)", T2.post(f"{P}/{sid}/end").status_code == 404)
tsock.get_received(); ssock.get_received()
r = T1.post(f"{P}/{sid}/end"); res = r.get_json()
check("end: present=3 absent=0 total=3", r.status_code == 200 and (res["present"], res["absent"], res["total"]) == (3, 0, 3) and res["status"] == "ended")
check("ending again is refused (409)", T1.post(f"{P}/{sid}/end").status_code == 409)
check("end pushes final state + 'ended' status live", any(e["name"] == "state" and e["args"][0]["status"] == "ended" for e in tsock.get_received())
      and any(e["name"] == "status" and e["args"][0]["status"] == "ended" for e in ssock.get_received()))
check("QR tokens deleted when the session ends", q("SELECT COUNT(*) FROM qr_tokens WHERE session_id=?", sid)[0][0] == 0)
check("scan after the end is rejected", scan(1, cur_tok).status_code in (400, 409))
check("join after the end is rejected (409)", S[2].post(f"/api/student/sessions/{sid}/join").status_code == 409)
check("ended session no longer in the student's open list", S[1].get("/api/student/sessions/active").get_json()["sessions"] == [])
check("teacher can open another session after ending", T1.post(P, json={"section_id": 1}).status_code == 201)

# ------------------------------------------------------------ absent rows + percentages + cancel
sid2 = T1.get(f"{P}/current").get_json()["session"]["id"]
S[1].post(f"/api/student/sessions/{sid2}/join"); S[2].post(f"/api/student/sessions/{sid2}/join")
check("cancel a waiting session (200)", T1.post(f"{P}/{sid2}/cancel").status_code == 200)
check("cancelled session is deleted with its joins", q("SELECT COUNT(*) FROM attendance_sessions WHERE id=?", sid2)[0][0] == 0 and q("SELECT COUNT(*) FROM session_participants WHERE session_id=?", sid2)[0][0] == 0)

sid3 = T1.post(P, json={"section_id": 1, "duration_minutes": 5}).get_json()["id"]
S[1].post(f"/api/student/sessions/{sid3}/join"); S[2].post(f"/api/student/sessions/{sid3}/join")
check("cannot cancel a running session (409)", (T1.post(f"{P}/{sid3}/start"), T1.post(f"{P}/{sid3}/cancel"))[1].status_code == 409)
tk3 = svc.latest_token(cc, sid3, time.time()); scan(1, tk3)
r = T1.post(f"{P}/{sid3}/end").get_json()
check("session 3: student1 present; 2 and 3 absent (2 joined but never scanned)", (r["present"], r["absent"], r["total"]) == (1, 2, 3)
      and {x["name"] for x in r["absent_students"]} == {"Student2", "Student3"})
check("absent rows were saved in the DB", q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND status='absent'", sid3)[0][0] == 2)
p = S[1].get("/api/student/profile").get_json()
check("student 1 overall = 2 of 2 sessions = 100%", p["percentage"] == 100.0 and p["total"] == 2)
p = S[2].get("/api/student/profile").get_json()
check("student 2 overall = 1 of 2 = 50% and flagged low", p["percentage"] == 50.0 and p["is_low"] is True)
d = T1.get("/api/teacher/dashboard").get_json()
check("teacher dashboard now shows real numbers: 2 sessions today; low list has student 2 (50%) and 3 (50%)",
      d["stats"]["todays_sessions"] == 2 and {(x["name"], x["percentage"]) for x in d["low_attendance"]} == {("Student2", 50.0), ("Student3", 50.0)})

# ------------------------------------------------------------ automatic expiry (configurable duration)
sid4 = T1.post(P, json={"section_id": 1, "duration_minutes": 1}).get_json()["id"]
S[1].post(f"/api/student/sessions/{sid4}/join"); T1.post(f"{P}/{sid4}/start")
tk4 = svc.latest_token(cc, sid4, time.time())
cc.execute("UPDATE attendance_sessions SET started_at = ? WHERE id = ?", (svc.ts_to_str(time.time() - 61), sid4)); cc.commit()
r = scan(1, tk4)
check("scan after the session duration ran out is refused", r.status_code == 409 and "ended" in r.get_json()["error"])
check("session auto-ended with absent rows saved", q("SELECT status FROM attendance_sessions WHERE id=?", sid4)[0][0] == "ended" and q("SELECT COUNT(*) FROM attendance_records WHERE session_id=?", sid4)[0][0] == 3)

sid5 = T1.post(P, json={"section_id": 1, "duration_minutes": 1}).get_json()["id"]
T1.post(f"{P}/{sid5}/start")
cc.execute("UPDATE attendance_sessions SET started_at = ? WHERE id = ?", (svc.ts_to_str(time.time() - 120), sid5)); cc.commit()
tsock5 = socketio.test_client(app, flask_test_client=T1); tsock5.emit("watch", {"session_id": sid5}, callback=True); tsock5.get_received()
realtime.rotation_tick(cc, time.time())
ev5 = tsock5.get_received()
check("background tick auto-ends an expired session in the DB", q("SELECT status FROM attendance_sessions WHERE id=?", sid5)[0][0] == "ended")
check("...and pushes the final state to the watching teacher", any(e["name"] == "state" and e["args"][0]["status"] == "ended" for e in ev5))
check("...and no new QR is pushed for an ended session", all(e["name"] != "qr" for e in ev5))

# ------------------------------------------------------------ group sessions at service level (UI/API for groups comes next)
cc.execute("INSERT INTO groups(teacher_id,name) VALUES(1,'Project Team')"); gid = 1
cc.executemany("INSERT INTO group_members(group_id,student_id) VALUES(1,?)", [(1,), (4,)]); cc.commit()   # one student from A, one from B
trow = cc.execute("SELECT * FROM teachers WHERE id=1").fetchone()
gs = svc.create_group_session(cc, trow, gid, 10, time.time())
check("group session: total = 2 members (across sections)", svc.build_state(cc, svc.get_session(cc, gs), time.time())["total"] == 2)
check("group member from section B can see + join it; non-member cannot",
      [x["id"] for x in S[4].get("/api/student/sessions/active").get_json()["sessions"]] == [gs]
      and S[4].post(f"/api/student/sessions/{gs}/join").status_code == 200
      and S[2].post(f"/api/student/sessions/{gs}/join").status_code == 403)
gt = svc.start_session(cc, gs, time.time())
check("group member scans successfully; non-member is refused", scan(4, gt).status_code == 200 and scan(2, gt).status_code == 403)
svc.finalize_session(cc, gs, time.time())
check("group end: present=1 absent=1", (lambda s: (s["present"], s["absent"]))(svc.build_state(cc, svc.get_session(cc, gs), time.time())) == (1, 1))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
