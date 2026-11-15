"""Stage 5 tests: face verification, student requests, teacher edits (+audit), database migration.
Run from the project root:  python tests/test_stage5.py     (temporary databases only)
Face data here is synthetic numbers (128 per face); the real camera pipeline is tested in the browser test."""
import os, sys, tempfile, sqlite3, random, time, json, csv, io
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app
from database.db import init_db
from extensions import socketio
import config
from services import core, face, sessions as svc

config.REQUESTS_DURING_SESSION = True      # these tests exercise requests made WHILE a session runs (off by default; see test_stage7)
app = create_app(os.path.join(tempfile.mkdtemp(), "t5.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

rnd = random.Random(7)
def person(): return [rnd.gauss(0, 0.09) for _ in range(128)]            # a "face": norm ~1, other people are far away
def noisy(v, s=0.01): return [x + rnd.gauss(0, s) for x in v]               # same face, another frame (distance ~0.11)
FACES = {i: person() for i in range(1, 6)}

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Ms. Sharma"), ("t2@x.com", "Mr. Other")]:
    c.execute("INSERT INTO teachers(user_id,name,require_face) VALUES(?,?,1)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(2,'ECE')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(2,'A')")
for i, sec in [(1, 1), (2, 1), (3, 1), (4, 1), (5, 2)]:
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}", sec))
c.commit(); c.close()
def login(email, role):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in range(1, 6)}
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))
P, ST = "/api/teacher/sessions", "/api/student"
enroll = lambda i, samples=None: S[i].post(f"{ST}/face/enroll", json={"samples": samples or [noisy(FACES[i]) for _ in range(3)]})

# ================================================================ face enrollment
check("anonymous / teacher cannot enroll (401 / 403)", app.test_client().post(f"{ST}/face/enroll", json={}).status_code == 401 and T1.post(f"{ST}/face/enroll", json={}).status_code == 403)
check("not enrolled yet", S[1].get(f"{ST}/face").get_json()["enrolled"] is False)
check("fewer than 3 captures refused (400)", enroll(1, [noisy(FACES[1]), noisy(FACES[1])]).status_code == 400)
check("wrong-size face data refused (400)", enroll(1, [[0.1] * 5] * 3).status_code == 400)
check("non-numeric face data refused (400)", enroll(1, [["x"] * 128] * 3).status_code == 400)
check("huge values refused (400)", enroll(1, [[99.0] * 128] * 3).status_code == 400)
check("captures of DIFFERENT people refused (400)", enroll(1, [FACES[1], FACES[2], FACES[1]]).status_code == 400)
check("nothing stored after the refused attempts", q("SELECT COUNT(*) FROM students WHERE face_descriptor IS NOT NULL")[0][0] == 0)
check("good enrollment accepted (200)", enroll(1).status_code == 200 and S[1].get(f"{ST}/face").get_json()["enrolled"] is True)
check("enrolling twice refused (409) - only the teacher can reset", enroll(1).status_code == 409)
for i in (2, 3): enroll(i)
check("what is stored is 128 numbers, not an image", len(json.loads(q("SELECT face_descriptor FROM students WHERE id=1")[0][0])) == 128)
sl = T1.get("/api/teacher/students").get_json()["students"]
check("teacher's student list shows face_enrolled (R1-R3 yes, R4 no)", {s["roll_no"]: s["face_enrolled"] for s in sl} == {"R1": True, "R2": True, "R3": True, "R4": False})
check("teacher 2 cannot reset teacher 1's student (404); student cannot (403)", T2.post("/api/teacher/students/1/reset-face").status_code == 404 and S[1].post("/api/teacher/students/1/reset-face").status_code == 403)
enroll(4); check("student 4 enrolls, teacher resets it, student 4 can enroll again", T1.post("/api/teacher/students/4/reset-face").status_code == 200 and S[4].get(f"{ST}/face").get_json()["enrolled"] is False and enroll(4).status_code == 200 and T1.post("/api/teacher/students/4/reset-face").status_code == 200)

# ================================================================ face-gated joining
sid = T1.post(P, json={"section_id": 1, "duration_minutes": 10}).get_json()["id"]
info = S[1].get(f"{ST}/sessions/{sid}").get_json()
check("session info tells the page: face required + student enrolled", info["face_required"] is True and info["face_enrolled"] is True)
r = S[1].post(f"{ST}/sessions/{sid}/join")
check("plain join is REFUSED when the teacher requires face scan (403, code face_required)", r.status_code == 403 and r.get_json()["code"] == "face_required")
check("student 5 (other teacher) cannot join (403)", S[5].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": FACES[5]}).status_code == 403)
check("student 1 with the RIGHT face joins (200)", S[1].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[1])}).status_code == 200)
check("joined row exists", q("SELECT COUNT(*) FROM session_participants WHERE session_id=? AND student_id=1", sid)[0][0] == 1)
check("joining again is harmless (already_joined)", S[1].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[1])}).get_json()["already_joined"] is True)
r = S[2].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[1])})
check("IMPERSONATION: student 2's account with student 1's face is refused (403 face_mismatch)", r.status_code == 403 and r.get_json()["code"] == "face_mismatch")
check("...and student 2 did not join", q("SELECT COUNT(*) FROM session_participants WHERE session_id=? AND student_id=2", sid)[0][0] == 0)
check("a half-similar face (distance ~0.7) is refused too", S[2].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[2], 0.06)}).status_code == 403)
check("bad descriptor refused (400)", S[2].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": [1, 2, 3]}).status_code == 400)
check("missing descriptor refused", S[2].post(f"{ST}/sessions/{sid}/join-face", json={}).status_code in (400, 403))
r = S[2].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[2])})
check("student 2 with their OWN face joins", r.status_code == 200)

# lock-out after repeated wrong faces (stops guessing)
core.lockout_reset_all()
codes = [S[3].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[1])}).status_code for _ in range(5)]
r = S[3].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[3])})
check("5 wrong faces in a row -> even the RIGHT face is locked out (429, face_locked)", codes == [403] * 5 and r.status_code == 429 and r.get_json()["code"] == "face_locked")
core.lockout_clear(3); core.lockout_seed(3, time.time() - 120, 5)
check("after the wait the right face works again", S[3].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": noisy(FACES[3])}).status_code == 200)
check("a success clears the failure count", core.lockout_count(3) == 0)

# settings toggle
check("settings expose require_face = true", T1.get("/api/teacher/settings").get_json()["require_face"] is True)
base = {"name": "Ms. Sharma", "phone": "", "warning_threshold": 75, "session_minutes": 10}
check("saving settings WITHOUT the key keeps the toggle", T1.put("/api/teacher/settings", json=base).get_json()["require_face"] is True)
check("student cannot toggle (403)", S[1].put("/api/teacher/settings", json={**base, "require_face": False}).status_code == 403)

# ================================================================ requests (student failed to join)
# student 4 has no enrolled face -> cannot join -> asks the teacher
r = S[4].post(f"{ST}/sessions/{sid}/join-face", json={"descriptor": FACES[4]}); check("un-enrolled student cannot join with face (409, not_enrolled)", r.status_code == 409 and r.get_json()["code"] == "not_enrolled")
tsock = socketio.test_client(app, flask_test_client=T1); tsock.emit("watch", {"session_id": sid}, callback=True)
ssock = socketio.test_client(app, flask_test_client=S[4]); ssock.emit("watch", {"session_id": sid}, callback=True); tsock.get_received(); ssock.get_received()
check("student 5 (other teacher) cannot ask (403)", S[5].post(f"{ST}/sessions/{sid}/request", json={}).status_code == 403)
check("teacher cannot use the student request API (403)", T1.post(f"{ST}/sessions/{sid}/request", json={}).status_code == 403)
check("over-long message refused (400)", S[4].post(f"{ST}/sessions/{sid}/request", json={"message": "x" * 300}).status_code == 400)
r = S[4].post(f"{ST}/sessions/{sid}/request", json={"message": "My camera is broken"}); check("student 4 sends a request (200)", r.status_code == 200)
ev = [e for e in tsock.get_received() if e["name"] == "state"]
check("teacher gets the request LIVE with the message", ev and ev[-1]["args"][0]["requests"][0]["name"] == "Student4" and ev[-1]["args"][0]["requests"][0]["message"] == "My camera is broken")
check("duplicate request refused (409)", S[4].post(f"{ST}/sessions/{sid}/request", json={}).status_code == 409)
check("student's page sees my_request = pending", S[4].get(f"{ST}/sessions/{sid}").get_json()["my_request"] == "pending")
rid = T1.get(f"{P}/{sid}").get_json()["requests"][0]["id"]
check("teacher 2 cannot accept (404); student cannot accept (403)", T2.post(f"{P}/requests/{rid}/accept").status_code == 404 and S[4].post(f"{P}/requests/{rid}/accept").status_code == 403)
check("student 4 is NOT present yet", q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND student_id=4", sid)[0][0] == 0)
tsock.get_received(); ssock.get_received()
check("teacher accepts the request (200)", T1.post(f"{P}/requests/{rid}/accept").status_code == 200)
check("student 4 is now PRESENT, marked via 'request'", q("SELECT status, marked_via FROM attendance_records WHERE session_id=? AND student_id=4", sid) == [("present", "request")])
check("and counted as having joined", q("SELECT COUNT(*) FROM session_participants WHERE session_id=? AND student_id=4", sid)[0][0] == 1)
check("student's page: my_request approved, my_status present", (lambda j: (j["my_request"], j["my_status"]))(S[4].get(f"{ST}/sessions/{sid}").get_json()) == ("approved", "present"))
check("student is told live (status push)", any(e["name"] == "status" for e in ssock.get_received()))
check("teacher's pending list is empty again", T1.get(f"{P}/{sid}").get_json()["requests"] == [])
check("accepting twice refused (409)", T1.post(f"{P}/requests/{rid}/accept").status_code == 409)
check("audit: request approval logged", q("SELECT old_status, new_status, kind FROM attendance_edits WHERE session_id=? AND student_id=4", sid) == [(None, "present", "request")])

# rejection
c = sqlite3.connect(dbp); c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,1)", (c.execute("INSERT INTO users(email,password_hash,role) VALUES('s6@x.com',?, 'student')", (generate_password_hash("secret123"),)).lastrowid, "R6", "Student6")); c.commit(); c.close()
S[6] = login("s6@x.com", "student")
S[6].post(f"{ST}/sessions/{sid}/request", json={}); rid6 = T1.get(f"{P}/{sid}").get_json()["requests"][0]["id"]
check("teacher rejects (200)", T1.post(f"{P}/requests/{rid6}/reject").status_code == 200)
check("rejected student: my_request rejected, NOT present", (lambda j: (j["my_request"], j["my_status"]))(S[6].get(f"{ST}/sessions/{sid}").get_json()) == ("rejected", None) and q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND student_id=6", sid)[0][0] == 0)
r = S[6].post(f"{ST}/sessions/{sid}/request", json={}); check("cannot re-ask after a rejection (409, 'declined')", r.status_code == 409 and "declined" in r.get_json()["error"])

# ================================================================ start; live manual marking; requests during the running session
check("manual mark is refused while still in the waiting room (409)", T1.post(f"{P}/{sid}/mark", json={"student_id": 3, "status": "present"}).status_code == 409)
check("teacher starts attendance", T1.post(f"{P}/{sid}/start").status_code == 200)
tok = q("SELECT token FROM qr_tokens ORDER BY expires_at DESC LIMIT 1")[0][0]
st = T1.get(f"{P}/{sid}").get_json()
check("running state has NO manual-marking list any more", "not_present_students" not in st)
check("manual mark is refused while the session is running (409)", T1.post(f"{P}/{sid}/mark", json={"student_id": 3, "status": "present"}).status_code == 409
      and q("SELECT COUNT(*) FROM attendance_records WHERE session_id=? AND student_id=3", sid)[0][0] == 0)
check("teacher 2 (404) / student (403) cannot mark", T2.post(f"{P}/{sid}/mark", json={"student_id": 3, "status": "present"}).status_code == 404 and S[1].post(f"{P}/{sid}/mark", json={"student_id": 3, "status": "present"}).status_code == 403)

# a request is cancelled automatically if the student then scans successfully
S[2].post(f"{ST}/sessions/{sid}/request", json={"message": "scanner slow"})
check("student 2's request is pending", [r["name"] for r in T1.get(f"{P}/{sid}").get_json()["requests"]] == ["Student2"])
check("student 2 then scans the QR fine (200)", S[2].post(f"{ST}/attendance/scan", json={"token": tok}).status_code == 200)
check("their pending request disappeared (cancelled, teacher not bothered)", T1.get(f"{P}/{sid}").get_json()["requests"] == [] and q("SELECT status FROM attendance_requests WHERE student_id=2")[0][0] == "cancelled")
check("a present student cannot send a request (409)", S[1].post(f"{ST}/attendance/scan", json={"token": tok}).status_code == 200 and S[1].post(f"{ST}/sessions/{sid}/request", json={}).status_code == 409)

# a request still pending when the session ends
S[3].post(f"{ST}/sessions/{sid}/request", json={"message": "I was in the lab"}); rid3 = T1.get(f"{P}/{sid}").get_json()["requests"][0]["id"]
res = T1.post(f"{P}/{sid}/end").get_json()
check("end: present = S1, S2, S4 (3 of 5 eligible); absent = S3, S6", (res["present"], res["absent"], res["total"]) == (3, 2, 5) and {x["name"] for x in res["absent_students"]} == {"Student3", "Student6"})
check("the pending request survives the end (teacher can still decide)", [r["name"] for r in res["requests"]] == ["Student3"])
check("a student rejected during the session still cannot re-ask after it ended (409, declined; late requests are tested in test_stage6)", (lambda r: r.status_code == 409 and "declined" in r.get_json()["error"])(S[6].post(f"{ST}/sessions/{sid}/request", json={})))

# ================================================================ edits after the session (and percentages follow)
pct = lambda i: S[i].get(f"{ST}/profile").get_json()["percentage"]
check("before edits: S3 = 0%, S1 = 100%", pct(3) == 0.0 and pct(1) == 100.0)
check("accepting the late request marks Student3 present (200)", T1.post(f"{P}/requests/{rid3}/accept").status_code == 200)
check("...the record flipped absent -> present via 'request'; total unchanged", q("SELECT status, marked_via FROM attendance_records WHERE session_id=? AND student_id=3", sid) == [("present", "request")]
      and q("SELECT total_students FROM attendance_sessions WHERE id=?", sid)[0][0] == 5)
check("Student3's percentage followed immediately (100%)", pct(3) == 100.0)
H = f"/api/teacher/history/{sid}/records"
r = T1.put(H, json={"student_id": 1, "status": "absent"}); j = r.get_json()
check("teacher edits an ENDED session: S1 present -> absent (200), summary recalculated", r.status_code == 200 and (j["present"], j["absent"]) == (3, 2) and j["percentage"] == 60.0)
check("S1's own percentage dropped to 0%", pct(1) == 0.0)
check("edit marks the row as made by the teacher", q("SELECT status, marked_via FROM attendance_records WHERE session_id=? AND student_id=1", sid) == [("absent", "teacher")])
check("edit back: S1 -> present (percentage 100% again)", T1.put(H, json={"student_id": 1, "status": "present"}).status_code == 200 and pct(1) == 100.0)
check("no-op edit (already present) writes no audit row", (lambda n: (T1.put(H, json={"student_id": 1, "status": "present"}), q("SELECT COUNT(*) FROM attendance_edits")[0][0] == n)[1])(q("SELECT COUNT(*) FROM attendance_edits")[0][0]))
check("history edit: bad status 400, outsider 400, other teacher 404, student 403",
      T1.put(H, json={"student_id": 1, "status": "x"}).status_code == 400 and T1.put(H, json={"student_id": 5, "status": "present"}).status_code == 400
      and T2.put(H, json={"student_id": 1, "status": "present"}).status_code == 404 and S[1].put(H, json={"student_id": 1, "status": "present"}).status_code == 403)
check("history edit is refused for a session that has not ended (404)", T1.put("/api/teacher/history/999/records", json={"student_id": 1, "status": "present"}).status_code == 404)
aud = q("SELECT student_id, old_status, new_status, kind FROM attendance_edits WHERE session_id=? ORDER BY id", sid)
check("audit trail is exactly: S4 request, S3 late request, S1 absent edit + restore (QR scans are not edits)", aud == [
    (4, None, "present", "request"),
    (3, "absent", "present", "request"), (1, "present", "absent", "edit"), (1, "absent", "present", "edit")])
rows = list(csv.reader(io.StringIO(T1.get(f"/api/teacher/history/{sid}.csv").get_data(as_text=True).lstrip("\ufeff"))))
by = {r[1]: r[4] for r in rows[1:]}
check("session CSV 'Marked by': QR scan / Teacher edit / Request approved", by["Student2"] == "QR scan" and by["Student1"] == "Teacher edit" and by["Student3"] == "Request approved" and by["Student4"] == "Request approved")

# nothing secret leaks
blob = " ".join(x.get_data(as_text=True) for x in [T1.get("/api/teacher/students"), T1.get("/api/teacher/dashboard"), T1.get(f"/api/teacher/history/{sid}"), T1.get(f"{P}/{sid}"),
                 T1.get("/api/teacher/reports"), S[1].get(f"{ST}/sessions/{sid}"), S[1].get(f"{ST}/profile"), S[1].get(f"{ST}/attendance"), S[1].get(f"{ST}/face")])
check("the face template is never sent to any browser", "face_descriptor" not in blob and str(round(FACES[1][0], 4))[:6] not in blob)

# ================================================================ face switched off -> plain join works again
T1.put("/api/teacher/settings", json={**base, "require_face": False})
sid2 = T1.post(P, json={"section_id": 1}).get_json()["id"]
check("with face OFF the normal join works for a student who never enrolled", S[6].post(f"{ST}/sessions/{sid2}/join").status_code == 200 and S[6].get(f"{ST}/sessions/{sid2}").get_json()["face_required"] is False)
T1.post(f"{P}/{sid2}/cancel")

# ================================================================ migration of an old database
old = os.path.join(tempfile.mkdtemp(), "old.db"); init_db(old)
oc = sqlite3.connect(old)
oc.execute("INSERT INTO users(email,password_hash,role) VALUES('a@x.com','h','teacher')"); oc.execute("INSERT INTO teachers(user_id,name) VALUES(1,'Old Teacher')")
oc.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'C')"); oc.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')")
oc.execute("INSERT INTO users(email,password_hash,role) VALUES('b@x.com','h','student')"); oc.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(2,'R1','Old Student',1)")
oc.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,label,status,duration_minutes,total_students) VALUES(1,'normal',1,'C - A','ended',10,1)")
oc.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(1,1,'present')"); oc.commit()
for stmt in ("ALTER TABLE teachers DROP COLUMN require_face", "ALTER TABLE students DROP COLUMN face_descriptor", "ALTER TABLE students DROP COLUMN face_enrolled_at",
             "ALTER TABLE attendance_records DROP COLUMN marked_via", "DROP TABLE attendance_requests", "DROP TABLE attendance_edits"):
    oc.execute(stmt)
oc.commit(); oc.close()
cols = lambda t: {r[1] for r in sqlite3.connect(old).execute(f"PRAGMA table_info({t})")}
check("simulated OLD database really lacks the new columns", "require_face" not in cols("teachers") and "marked_via" not in cols("attendance_records"))
init_db(old); init_db(old)       # upgrade (twice: must be safe to repeat)
oc = sqlite3.connect(old)
check("upgrade adds the new columns and tables", {"require_face"} <= cols("teachers") and {"face_descriptor", "face_enrolled_at"} <= cols("students") and "marked_via" in cols("attendance_records")
      and oc.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('attendance_requests','attendance_edits')").fetchone()[0] == 2)
check("old data is intact; defaults: face OFF, marked via 'qr'", oc.execute("SELECT name, require_face FROM teachers").fetchall() == [("Old Teacher", 0)]
      and oc.execute("SELECT status, marked_via FROM attendance_records").fetchall() == [("present", "qr")] and oc.execute("SELECT name FROM students").fetchall() == [("Old Student",)])

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
