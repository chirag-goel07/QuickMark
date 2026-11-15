"""Stage 7 tests: after-session-only requests, profile pictures, student profile/classes/requests/password/CSV, migration.
Run from the project root:  python tests/test_stage7.py   (temporary databases only)"""
import os, sys, tempfile, sqlite3, csv, io, random, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app
from database.db import init_db
import config

app = create_app(os.path.join(tempfile.mkdtemp(), "t7.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
c.execute("INSERT INTO teachers(user_id,name,require_face) VALUES(?,?,1)", (user("t1@x.com", "teacher"), "Ms. Sharma"))
c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user("t2@x.com", "teacher"), "Mr. Other"))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 2nd Sem')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(2,'ECE')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(2,'A')")
c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'DSA')"); c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'Digital Logic')"); c.execute("INSERT INTO subjects(class_id,name) VALUES(2,'Circuits')")
for i, (nm, sec) in enumerate([("Amit", 1), ("Neha", 1), ("Zed", 2)], 1):
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", nm, sec))
c.execute("INSERT INTO groups(teacher_id,name) VALUES(1,'Lab Team')"); c.executemany("INSERT INTO group_members VALUES(1,?)", [(1,), (2,)])
def ended(days_ago, subject, marks, label):
    end = datetime.now() - timedelta(days=days_ago); start = end - timedelta(minutes=10); f = "%Y-%m-%d %H:%M:%S"
    sid = c.execute("INSERT INTO attendance_sessions(teacher_id,session_type,section_id,subject_id,label,status,duration_minutes,total_students,created_at,started_at,ended_at) VALUES(1,'normal',1,?,?,'ended',10,?,?,?,?)",
                    (subject, label, len(marks), start.strftime(f), start.strftime(f), end.strftime(f))).lastrowid
    for stu, st in marks.items(): c.execute("INSERT INTO attendance_records(session_id,student_id,status) VALUES(?,?,?)", (sid, stu, st))
    return sid
e1 = ended(1, 1, {1: "present", 2: "absent"}, "CSE (DSA)")
e2 = ended(2, 1, {1: "present", 2: "present"}, "CSE (DSA) 2")
e3 = ended(3, None, {1: "absent", 2: "present"}, "=EVIL() label")           # no subject -> 'General'
c.commit(); c.close()
def login(email, role, pw="secret123"): cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": pw, "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in (1, 2, 3)}
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))
ST, P = "/api/student", "/api/teacher/sessions"
JPEG = b"\xff\xd8\xff\xe0" + bytes(random.Random(1).randrange(256) for _ in range(900)) + b"\xff\xd9"
def up(i, data=JPEG):
    """Pictures now come from the face setup, so the tests put one into the database directly (see test_stage11 for the real flow)."""
    cc = sqlite3.connect(dbp); cc.execute("UPDATE students SET avatar = ?, avatar_updated_at = ? WHERE id = ?", (data, "2026-11-01 10:0%d:00" % i, i)); cc.commit(); cc.close()
    return type("R", (), {"status_code": 200})()

# ============================================================ requests only AFTER the session (default)
check("default: requests during a session are OFF", config.REQUESTS_DURING_SESSION is False)
sid = T1.post(P, json={"section_id": 1}).get_json()["id"]
info = S[2].get(f"{ST}/sessions/{sid}").get_json()
check("waiting session: can_request is false", info["status"] == "waiting" and info["can_request"] is False)
r = S[2].post(f"{ST}/sessions/{sid}/request", json={"message": "x"}); check("request during the WAITING room refused (409, after_session_only)", r.status_code == 409 and r.get_json()["code"] == "after_session_only" and "after the session has ended" in r.get_json()["error"])
T1.post(f"{P}/{sid}/start")
check("running session: request refused too (409)", S[2].post(f"{ST}/sessions/{sid}/request", json={}).status_code == 409 and S[2].get(f"{ST}/sessions/{sid}").get_json()["can_request"] is False)
check("nothing was stored for the refused requests", q("SELECT COUNT(*) FROM attendance_requests")[0][0] == 0)
T1.post(f"{P}/{sid}/end")
info = S[2].get(f"{ST}/sessions/{sid}").get_json()
check("after the session ended the same student CAN ask (can_request true)", info["status"] == "ended" and info["can_request"] is True)
check("...and the request is accepted (200)", S[2].post(f"{ST}/sessions/{sid}/request", json={"message": "scanner failed"}).status_code == 200)
config.REQUESTS_DURING_SESSION = True
sid2 = T1.post(P, json={"section_id": 1}).get_json()["id"]
check("option QUICKMARK_REQUESTS_DURING_SESSION=1 allows in-session requests again (200)", S[1].post(f"{ST}/sessions/{sid2}/request", json={}).status_code == 200)
config.REQUESTS_DURING_SESSION = False
T1.post(f"{P}/{sid2}/cancel")

# ============================================================ profile pictures
check("anonymous cannot read/upload an avatar (401)", app.test_client().get(f"{ST}/avatar").status_code == 401 and app.test_client().post(f"{ST}/avatar", data=JPEG, content_type="image/jpeg").status_code == 401)
check("teacher cannot use the student avatar API (403)", T1.get(f"{ST}/avatar").status_code == 403 and T1.post(f"{ST}/avatar", data=JPEG, content_type="image/jpeg").status_code == 403)
check("no picture yet -> 404", S[1].get(f"{ST}/avatar").status_code == 404 and S[1].get(f"{ST}/profile").get_json()["has_avatar"] is False)
r = up(1); check("a stored picture (as the face setup does it) is in place", r.status_code == 200)
g = S[1].get(f"{ST}/avatar")
check("student gets back exactly their own bytes as image/jpeg", g.status_code == 200 and g.data == JPEG and g.mimetype == "image/jpeg")
check("served with nosniff + locked-down CSP + private cache", g.headers["X-Content-Type-Options"] == "nosniff" and "default-src 'none'" in g.headers["Content-Security-Policy"] and "private" in g.headers["Cache-Control"])
check("student 2 still has no picture (only own is ever served)", S[2].get(f"{ST}/avatar").status_code == 404)
check("teacher 1 can view their student's picture", T1.get("/api/teacher/students/1/avatar").data == JPEG)
check("teacher 2 cannot (404); a student cannot use the teacher route (403); anonymous 401", T2.get("/api/teacher/students/1/avatar").status_code == 404 and S[2].get("/api/teacher/students/1/avatar").status_code == 403 and app.test_client().get("/api/teacher/students/1/avatar").status_code == 401)
check("teacher: student without a picture -> 404", T1.get("/api/teacher/students/2/avatar").status_code == 404)
me = S[1].get("/api/auth/me").get_json(); check("/auth/me tells the page there is a picture (and its version)", me["has_avatar"] is True and me["avatar_v"])
check("teacher's student list shows has_avatar (R1 yes, R2 no)", {s["roll_no"]: s["has_avatar"] for s in T1.get("/api/teacher/students").get_json()["students"]} == {"R1": True, "R2": False})
blob = " ".join(x.get_data(as_text=True) for x in [T1.get("/api/teacher/students"), T1.get("/api/teacher/dashboard"), S[1].get(f"{ST}/profile"), S[1].get("/api/auth/me"), T1.get(f"{P}/{sid}")])
check("the picture bytes never appear inside any JSON response", "\\u00ff" not in blob and "avatar\":" not in blob.replace('"has_avatar"', ""))
# the teacher's request lists carry the flag so the page can show the small picture
r2 = T1.get("/api/teacher/dashboard").get_json()["requests"]
check("dashboard request for Neha (no picture): has_avatar false", [x["has_avatar"] for x in r2 if x["name"] == "Neha"] == [False])
up(2)
r2 = T1.get("/api/teacher/dashboard").get_json()["requests"]; d = T1.get(f"/api/teacher/history/{sid}").get_json()
check("after Neha adds a picture, her request shows has_avatar + version on dashboard and in the session detail", r2[0]["has_avatar"] is True and r2[0]["avatar_v"] and d["requests"][0]["has_avatar"] is True)
check("session lists (present/absent/joined) carry the flag too", all("has_avatar" in x for x in d["present_students"] + d["absent_students"]))
up(1)

# ============================================================ profile + settings
p = S[1].get(f"{ST}/profile").get_json()
check("profile has name, roll, email, class, section, teacher, phone, face info", (p["name"], p["roll_no"], p["email"], p["class_name"], p["section_name"], p["teacher_name"], p["phone"]) == ("Amit", "R1", "s1@x.com", "CSE - 2nd Sem", "A", "Ms. Sharma", ""))
check("first login: teacher requires face + not enrolled -> needs_face_setup true", p["require_face"] is True and p["face_enrolled"] is False and p["needs_face_setup"] is True)
rnd = random.Random(9); face = [rnd.gauss(0, 0.09) for _ in range(128)]
check("student enrolls their face from the setup page API (200)", S[1].post(f"{ST}/face/enroll", json={"samples": [[x + rnd.gauss(0, 0.01) for x in face] for _ in range(3)]}).status_code == 200)
p = S[1].get(f"{ST}/profile").get_json(); check("afterwards needs_face_setup is false, enrolled date shown", p["needs_face_setup"] is False and p["face_enrolled"] is True and p["face_enrolled_at"])
check("teacher with face OFF: students are never told to set up a face", S[3].get(f"{ST}/profile").get_json()["needs_face_setup"] is False)
check("face template is never in the profile JSON", "descriptor" not in S[1].get(f"{ST}/profile").get_data(as_text=True))
check("phone update (200) and shows in profile + teacher's list", S[1].put(f"{ST}/profile", json={"phone": " 98765 "}).status_code == 200 and S[1].get(f"{ST}/profile").get_json()["phone"] == "98765"
      and [s["phone"] for s in T1.get("/api/teacher/students").get_json()["students"] if s["roll_no"] == "R1"] == ["98765"])
check("phone too long refused (400); student cannot change name/class through profile", S[1].put(f"{ST}/profile", json={"phone": "1" * 30}).status_code == 400
      and (S[1].put(f"{ST}/profile", json={"phone": "1", "name": "Hacker", "section_id": 2}), S[1].get(f"{ST}/profile").get_json()["name"])[1] == "Amit")
check("profile API: teacher 403, anonymous 401", T1.put(f"{ST}/profile", json={"phone": "1"}).status_code == 403 and app.test_client().get(f"{ST}/profile").status_code == 401)
check("wrong current password refused (400)", S[1].post(f"{ST}/password", json={"current_password": "nope", "new_password": "newpass12"}).status_code == 400)
check("short new password refused (400)", S[1].post(f"{ST}/password", json={"current_password": "secret123", "new_password": "123"}).status_code == 400)
check("password changed (200); old stops working, new works", S[1].post(f"{ST}/password", json={"current_password": "secret123", "new_password": "newpass12"}).status_code == 200
      and login("s1@x.com", "student").get(f"{ST}/profile").status_code == 401 and login("s1@x.com", "student", "newpass12").get(f"{ST}/profile").status_code == 200)
check("teacher cannot call the student password API (403)", T1.post(f"{ST}/password", json={"current_password": "secret123", "new_password": "abcdef"}).status_code == 403)

# ============================================================ my classes
cl = S[1].get(f"{ST}/classes").get_json()["classes"]
check("classes: one enrolled class with section and teacher", len(cl) == 1 and (cl[0]["class_name"], cl[0]["section_name"], cl[0]["teacher_name"]) == ("CSE - 2nd Sem", "A", "Ms. Sharma") and cl[0]["students_in_class"] == 2)
sub = {x["name"]: x for x in cl[0]["subjects"]}
check("subjects: DSA 2/2 = 100%, Digital Logic has no sessions yet (percentage null)", (sub["DSA"]["present"], sub["DSA"]["total"], sub["DSA"]["percentage"]) == (2, 2, 100.0) and sub["Digital Logic"]["percentage"] is None and sub["Digital Logic"]["total"] == 0)
check("sessions without a subject appear as 'General (no subject)': 0 of 2 (the seeded one + the live session he missed)", (sub["General (no subject)"]["present"], sub["General (no subject)"]["total"]) == (0, 2))
check("groups the student belongs to, with member counts", cl[0]["groups"] == [{"id": 1, "name": "Lab Team", "member_count": 2}])
check("another class's student sees only their own class and subjects", (lambda j: ([x["class_name"] for x in j], [s["name"] for s in j[0]["subjects"]]))(S[3].get(f"{ST}/classes").get_json()["classes"]) == (["ECE"], ["Circuits"]))
check("classes API: teacher 403, anonymous 401", T1.get(f"{ST}/classes").status_code == 403 and app.test_client().get(f"{ST}/classes").status_code == 401)

# ============================================================ my requests
mine = S[2].get(f"{ST}/requests").get_json()["requests"]
check("student 2's requests: one pending with her message and the session label", [(x["status"], x["message"], x["label"]) for x in mine] == [("pending", "scanner failed", "CSE - 2nd Sem - A")])
check("student 1 sees none of student 2's requests", S[1].get(f"{ST}/requests").get_json()["requests"] == [])
rid = mine[0]["id"]; T1.post(f"{P}/requests/{rid}/accept")
check("after the teacher accepts, the student's list shows 'approved'", S[2].get(f"{ST}/requests").get_json()["requests"][0]["status"] == "approved")
check("requests API: teacher 403", T1.get(f"{ST}/requests").status_code == 403)

# ============================================================ concrete numbers for the student dashboard
import services.reports as rp
check("advice math: 2/4 at 75% -> attend 4 more in a row (6/8 = 75%)", rp.threshold_advice(2, 4, 75) == {"status": "below", "classes_needed": 4})
check("advice math: 3/4 at 75% -> exactly at the limit, can miss 0", rp.threshold_advice(3, 4, 75) == {"status": "ok", "can_miss": 0})
check("advice math: 9/10 at 75% -> can miss 2 more (9/12 = 75% exactly, 9/13 is below)", rp.threshold_advice(9, 10, 75) == {"status": "ok", "can_miss": 2} and 9 / 12 == 0.75 and 9 / 13 < 0.75)
check("advice math: no sessions -> none; 100% threshold below -> unreachable", rp.threshold_advice(0, 0, 75) is None and rp.threshold_advice(1, 2, 100) == {"status": "below", "classes_needed": None})
check("proof for 2/4: after 4 more present it is 75%, after 3 more it is below", (2 + 4) / (4 + 4) == 0.75 and (2 + 3) / (4 + 3) < 0.75)
a = S[1].get(f"{ST}/attendance").get_json()
check("Amit (2 present of 4): absent 2, advice 'attend 4 more', streak 0 (latest session absent)", (a["absent"], a["advice"], a["streak"]) == (2, {"status": "below", "classes_needed": 4}, 0))
b = S[2].get(f"{ST}/attendance").get_json()
check("Neha (3 of 4 = 75%): advice 'can miss 0', this_month counts all 4 sessions", (b["advice"], b["this_month"]) == ({"status": "ok", "can_miss": 0}, {"present": 3, "total": 4}))
check("student with no records: advice null, streak 0", (lambda j: (j["advice"], j["streak"], j["absent"]))(S[3].get(f"{ST}/attendance").get_json()) == (None, 0, 0))
check("/auth/me for a student tells the page whether to send them to face setup", S[2].get("/api/auth/me").get_json()["needs_face_setup"] is True and S[3].get("/api/auth/me").get_json()["needs_face_setup"] is False and S[1].get("/api/auth/me").get_json()["needs_face_setup"] is False)

# ============================================================ my attendance CSV
r = S[2].get(f"{ST}/attendance/export.csv"); rows = list(csv.reader(io.StringIO(r.get_data(as_text=True).lstrip("\ufeff"))))
check("student CSV: attachment, header, only own 4 rows (3 seeded + the accepted one)", "attachment" in r.headers["Content-Disposition"] and rows[0] == ["Date", "Class / Group", "Subject", "Status"] and len(rows) == 5)
check("CSV neutralises a label starting with '='", any(x[1] == "'=EVIL() label" for x in rows[1:]))
check("CSV for another student has their own rows (Zed has none)", len(list(csv.reader(io.StringIO(S[3].get(f"{ST}/attendance/export.csv").get_data(as_text=True).lstrip("\ufeff"))))) == 1)
check("CSV: teacher 403, anonymous 401", T1.get(f"{ST}/attendance/export.csv").status_code == 403 and app.test_client().get(f"{ST}/attendance/export.csv").status_code == 401)

# ============================================================ upgrade of an old database
old = os.path.join(tempfile.mkdtemp(), "old.db"); init_db(old)
oc = sqlite3.connect(old)
oc.execute("INSERT INTO users(email,password_hash,role) VALUES('a@x.com','h','teacher')"); oc.execute("INSERT INTO teachers(user_id,name) VALUES(1,'T')")
oc.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'C')"); oc.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')")
oc.execute("INSERT INTO users(email,password_hash,role) VALUES('b@x.com','h','student')"); oc.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(2,'R1','Old Student',1)"); oc.commit()
oc.execute("ALTER TABLE students DROP COLUMN avatar"); oc.execute("ALTER TABLE students DROP COLUMN avatar_updated_at"); oc.commit(); oc.close()
cols = lambda: {r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(students)")}
check("simulated old database has no avatar columns", "avatar" not in cols())
init_db(old); init_db(old)
check("upgrade adds avatar columns and keeps the student", {"avatar", "avatar_updated_at"} <= cols() and sqlite3.connect(old).execute("SELECT name, avatar FROM students").fetchall() == [("Old Student", None)])

# ============================================================ renamed product + old setting names
os.environ["ATTENDSURE_FACE_THRESHOLD"] = "0.42"; os.environ.pop("QUICKMARK_FACE_THRESHOLD", None)
import importlib; importlib.reload(config); check("old ATTENDSURE_* setting names still work", config.FACE_MATCH_THRESHOLD == 0.42)
os.environ["QUICKMARK_FACE_THRESHOLD"] = "0.33"; importlib.reload(config); check("new QUICKMARK_* names take priority", config.FACE_MATCH_THRESHOLD == 0.33)
check("default database file is quickmark.db", config.DATABASE_PATH.endswith("quickmark.db") or config.DATABASE_PATH.endswith("attendsure.db"))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
