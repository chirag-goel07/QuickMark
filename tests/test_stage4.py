"""Stage 4 tests: history, reports, CSV, settings, warning emails, student attendance view.
Run from the project root:  python tests/test_stage4.py   (temporary database + fake mail server only)"""
import os, sys, tempfile, sqlite3, csv, io

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend")); sys.path.insert(0, HERE)
from werkzeug.security import generate_password_hash
from app import create_app
import config
from smtp_sink import SmtpSink

app = create_app(os.path.join(tempfile.mkdtemp(), "t4.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

# ---------------------------------------------------------------- data
c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "Ms. Sharma"), ("t2@x.com", "Mr. Other")]:
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 2nd Sem')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CSE - 4th Sem')"); c.execute("INSERT INTO classes(teacher_id,name) VALUES(2,'ECE')")
c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'B')"); c.execute("INSERT INTO sections(class_id,name) VALUES(2,'A')"); c.execute("INSERT INTO sections(class_id,name) VALUES(3,'A')")
c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'DSA')"); c.execute("INSERT INTO subjects(class_id,name) VALUES(1,'Digital Logic')")
# students: 1 Amit(secA)  2 Neha(secA)  3 Rohan(secB)  4 =EVIL() (sec 3, class 2)  5 other teacher's student
for i, (nm, sec) in enumerate([("Amit", 1), ("Neha", 1), ("Rohan", 2), ("=EVIL()", 3), ("Zed", 4)], 1):
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,?)", (user(f"s{i}@x.com", "student"), f"R{i}", nm, sec))
def add_session(teacher, section, subject, day, status, marks, kind="normal", group=None, label="CSE - 2nd Sem - A"):
    sid = c.execute("""INSERT INTO attendance_sessions(teacher_id,session_type,section_id,group_id,subject_id,label,status,duration_minutes,total_students,created_at,started_at,ended_at)
                       VALUES(?,?,?,?,?,?,?,10,?,?,?,?)""",
                    (teacher, kind, section, group, subject, label, status, len(marks), f"{day} 09:00:00", f"{day} 09:00:00", f"{day} 09:10:00" if status == "ended" else None)).lastrowid
    for stu, st in marks.items():
        c.execute("INSERT INTO attendance_records(session_id,student_id,status,marked_at) VALUES(?,?,?,?)", (sid, stu, st, f"{day} 09:02:00"))
    return sid
P, A = "present", "absent"
s1 = add_session(1, 1, 1, "2026-10-01", "ended", {1: P, 2: P})                       # DSA
s2 = add_session(1, 1, 1, "2026-10-02", "ended", {1: P, 2: A})                       # DSA
s3 = add_session(1, 1, None, "2026-10-03", "ended", {1: A, 2: A})                    # no subject
s4 = add_session(1, 2, 2, "2026-10-03", "ended", {3: P}, label="CSE - 2nd Sem - B")  # Digital Logic, section B
c.execute("INSERT INTO groups(teacher_id,name) VALUES(1,'Lab Team')"); c.executemany("INSERT INTO group_members VALUES(1,?)", [(1,), (4,)])
s5 = add_session(1, None, None, "2026-10-04", "ended", {1: P, 4: A}, kind="group", group=1, label="Group: Lab Team")
s6 = add_session(1, 1, None, "2026-10-05", "waiting", {})                            # must NOT appear anywhere
s7 = add_session(2, 4, None, "2026-10-02", "ended", {5: P}, label="ECE - A")         # other teacher
c.commit(); c.close()
# Expected (teacher 1):  Amit P,P,A,P = 3/4 = 75.0 | Neha P,A,A = 1/3 = 33.3 | Rohan 1/1 = 100 | EVIL 0/1 = 0.0
def login(email, role="teacher", pw="secret123"):
    cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": pw, "role": role}); return cl
T1, T2 = login("t1@x.com"), login("t2@x.com")
S = {i: login(f"s{i}@x.com", "student") for i in range(1, 6)}
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))
def rows_of(resp): return list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip("\ufeff"))))
H = "/api/teacher/history"

# ---------------------------------------------------------------- history
check("history needs teacher login: anon 401, student 403", app.test_client().get(H).status_code == 401 and S[1].get(H).status_code == 403)
hs = T1.get(H).get_json()["sessions"]
check("history lists only ENDED sessions of this teacher (5), newest first", [h["id"] for h in hs] == [s5, s4, s3, s2, s1])
check("waiting session and other teacher's session not listed", all(h["id"] not in (s6, s7) for h in hs))
h1 = [h for h in hs if h["id"] == s1][0]
check("row math: s1 total 2, present 2, absent 0, 100.0%, subject DSA, date", (h1["total"], h1["present"], h1["absent"], h1["percentage"], h1["subject"], h1["date"]) == (2, 2, 0, 100.0, "DSA", "2026-10-01"))
h2 = [h for h in hs if h["id"] == s2][0]; check("row math: s2 = 1/2 = 50.0%", (h2["present"], h2["absent"], h2["percentage"]) == (1, 1, 50.0))
check("filter by type=group -> only the group session", [h["id"] for h in T1.get(H + "?type=group").get_json()["sessions"]] == [s5])
check("filter by class 1 (2nd Sem) -> 4 normal sessions, no group", sorted(h["id"] for h in T1.get(H + "?class_id=1").get_json()["sessions"]) == sorted([s1, s2, s3, s4]))
check("date range 2026-10-02..2026-10-03 -> s2, s3, s4", sorted(h["id"] for h in T1.get(H + "?from=2026-10-02&to=2026-10-03").get_json()["sessions"]) == sorted([s2, s3, s4]))
check("bad date format is ignored (no crash, all 5)", len(T1.get(H + "?from=garbage'; DROP TABLE x").get_json()["sessions"]) == 5)
check("teacher 2 sees only their own session", [h["id"] for h in T2.get(H).get_json()["sessions"]] == [s7])
d = T1.get(f"{H}/{s2}").get_json()
check("detail: present Amit, absent Neha, 50%", (d["present"], d["absent"], d["percentage"]) == (1, 1, 50.0) and [x["name"] for x in d["present_students"]] == ["Amit"] and [x["name"] for x in d["absent_students"]] == ["Neha"])
check("detail: other teacher 404, waiting session 404, student 403", T2.get(f"{H}/{s2}").status_code == 404 and T1.get(f"{H}/{s6}").status_code == 404 and S[1].get(f"{H}/{s2}").status_code == 403)
r = T1.get(H + "/export.csv"); rows = rows_of(r)
check("history CSV: attachment, header, 5 data rows", "attachment" in r.headers["Content-Disposition"] and rows[0][:3] == ["Date", "Class / Group", "Subject"] and len(rows) == 6)
check("history CSV honours filters", len(rows_of(T1.get(H + "/export.csv?type=group"))) == 2)
r = T1.get(f"{H}/{s5}.csv"); rows = rows_of(r)
check("session CSV: students with status", rows[0] == ["Roll No", "Name", "Status", "Marked at", "Marked by"] and {(x[1], x[2]) for x in rows[1:]} == {("Amit", "present"), ("=EVIL()".replace("=", "'="), "absent")})
check("CSV formula injection neutralised (name starting with '=' is prefixed)", any(x[1] == "'=EVIL()" for x in rows[1:]))
check("session CSV: other teacher 404", T2.get(f"{H}/{s5}.csv").status_code == 404)

# ---------------------------------------------------------------- reports
R = "/api/teacher/reports"
check("reports need teacher: anon 401, student 403", app.test_client().get(R).status_code == 401 and S[1].get(R).status_code == 403)
rep = T1.get(R).get_json()
check("overall counts: 5 ended sessions, 2 classes, 4 students", rep["overall"]["sessions"] == 5 and rep["overall"]["classes"] == 2 and rep["overall"]["students"] == 4)
# marks: Amit 3/4, Neha 1/3, Rohan 1/1, EVIL 0/1 -> present 5 of total 9 = 55.6
check("overall percentage = 5/9 = 55.6", rep["overall"]["percentage"] == 55.6)
st = {s["name"]: s for s in rep["students"]}
check("student-wise: Amit 75.0, Neha 33.3, Rohan 100.0, =EVIL() 0.0", (st["Amit"]["percentage"], st["Neha"]["percentage"], st["Rohan"]["percentage"], st["=EVIL()"]["percentage"]) == (75.0, 33.3, 100.0, 0.0))
check("threshold 75: Amit (exactly 75) is NOT low; Neha and =EVIL() are", [s["name"] for s in rep["low_students"]] == ["=EVIL()", "Neha"] and rep["overall"]["low"] == 2)
cl = {x["name"]: x for x in rep["classes"]}
check("class-wise numbers: 2nd Sem 3 students, present 5 / total 8 marks = 62.5%; 4th Sem 1 student 0/1 = 0.0%",
      (cl["CSE - 2nd Sem"]["students"], cl["CSE - 2nd Sem"]["present"], cl["CSE - 2nd Sem"]["total"], cl["CSE - 2nd Sem"]["percentage"]) == (3, 5, 8, 62.5)
      and (cl["CSE - 4th Sem"]["students"], cl["CSE - 4th Sem"]["percentage"]) == (1, 0.0))
sc = {(x["class_name"], x["section_name"]): x for x in rep["sections"]}
check("section-wise: 2nd Sem A = 4/7 (57.1%), B = 1/1 (100.0%)", sc[("CSE - 2nd Sem", "A")]["percentage"] == 57.1 and sc[("CSE - 2nd Sem", "B")]["percentage"] == 100.0)
check("trend: per-day percentages in date order", [(t["day"], t["percentage"]) for t in rep["trend"]] == [("2026-10-01", 100.0), ("2026-10-02", 50.0), ("2026-10-03", 33.3), ("2026-10-04", 50.0)])
check("teacher 2 sees only own data (1 student, 100%)", (lambda r: (r["overall"]["students"], r["overall"]["percentage"]))(T2.get(R).get_json()) == (1, 100.0))
for kind, n in [("students", 4), ("low", 2), ("classes", 2), ("sections", 3)]:
    r = T1.get(f"{R}/export.csv?kind={kind}"); check(f"report CSV kind={kind}: {n} data rows", r.status_code == 200 and len(rows_of(r)) == n + 1)
check("unknown report kind -> 400", T1.get(f"{R}/export.csv?kind=zzz").status_code == 400)
c = sqlite3.connect(dbp)
c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,2)", (c.execute("INSERT INTO users(email,password_hash,role) VALUES('new@x.com',?, 'student')", (generate_password_hash("secret123"),)).lastrowid, "R9", "NoData")); c.commit(); c.close()
check("student with no records has percentage null (not 0%) and is not low",
      (lambda s: s["percentage"] is None and s["is_low"] is False)([x for x in T1.get(R).get_json()["students"] if x["name"] == "NoData"][0]))

# ---------------------------------------------------------------- settings
SET = "/api/teacher/settings"
check("settings: student 403, anon 401", S[1].get(SET).status_code == 403 and app.test_client().get(SET).status_code == 401)
g = T1.get(SET).get_json(); check("settings returns profile + defaults (75, 10)", (g["name"], g["email"], g["warning_threshold"], g["session_minutes"]) == ("Ms. Sharma", "t1@x.com", 75, 10))
good = {"name": "Ms. Sharma", "phone": "99999", "warning_threshold": 75, "session_minutes": 10}
for label, bad in [("threshold 0", {"warning_threshold": 0}), ("threshold 101", {"warning_threshold": 101}), ("threshold text", {"warning_threshold": "abc"}),
                   ("threshold decimal", {"warning_threshold": "75.5"}), ("duration 0", {"session_minutes": 0}), ("duration 181", {"session_minutes": 181}),
                   ("blank name", {"name": " "}), ("long phone", {"phone": "1" * 30})]:
    check(f"settings rejects {label} (400)", T1.put(SET, json={**good, **bad}).status_code == 400)
r = T1.put(SET, json={"name": "Ms. S. Sharma", "phone": "12345", "warning_threshold": 60, "session_minutes": 20})
check("settings saved (name, phone, threshold 60, duration 20)", r.status_code == 200 and r.get_json()["warning_threshold"] == 60 and T1.get(SET).get_json()["name"] == "Ms. S. Sharma")
check("new threshold 60 applied: only =EVIL() (0%) and Neha (33.3%) still low, Amit fine", [s["name"] for s in T1.get(R).get_json()["low_students"]] == ["=EVIL()", "Neha"])
r = T1.put(SET, json={**good, "warning_threshold": 30}); lows = [s["name"] for s in T1.get(R).get_json()["low_students"]]
check("threshold 30: Neha (33.3%) is no longer low; =EVIL() (0%) still is", lows == ["=EVIL()"])
check("dashboard follows the threshold too", [x["name"] for x in T1.get("/api/teacher/dashboard").get_json()["low_attendance"]] == ["=EVIL()"])
T1.put(SET, json={**good, "warning_threshold": 75, "session_minutes": 20})
check("default session duration setting reaches the session screen", T1.get("/api/teacher/sessions/current").get_json()["default_duration"] == 20)
check("teacher 2's settings untouched by teacher 1's changes", T2.get(SET).get_json()["warning_threshold"] == 75)
check("wrong current password refused", T1.post(SET + "/password", json={"current_password": "nope", "new_password": "newsecret1"}).status_code == 400)
check("short new password refused", T1.post(SET + "/password", json={"current_password": "secret123", "new_password": "123"}).status_code == 400)
check("password changed (200)", T1.post(SET + "/password", json={"current_password": "secret123", "new_password": "newsecret1"}).status_code == 200)
check("old password stops working; new one works", login("t1@x.com").get(SET).status_code == 401 and login("t1@x.com", pw="newsecret1").get(SET).status_code == 200)
T1 = login("t1@x.com", pw="newsecret1")
T1.put(SET, json={**good, "warning_threshold": 75, "session_minutes": 10})

# ---------------------------------------------------------------- emails: drafts (mailto)
E = "/api/teacher/emails"
low = T1.get("/api/teacher/dashboard").get_json()["low_attendance"]
neha = [x for x in low if x["name"] == "Neha"][0]
check("dashboard low rows carry the student's email", neha["email"] == "s2@x.com")
check("warning text has student name, percentage 33.3%, threshold 75% and teacher name",
      all(w in neha["body"] for w in ("Dear Neha", "33.3%", "75%", "Ms. Sharma")) and "33.3%" in neha["subject"] and "75%" in neha["subject"])
check("students list gives low students their warning text too", [s for s in T1.get("/api/teacher/students?low=1").get_json()["students"] if s["name"] == "Neha"][0]["warning_body"] == neha["body"])
check("non-low student has no warning text", all("warning_body" not in s for s in T1.get("/api/teacher/students").get_json()["students"] if not s["is_low"]))
b = T1.get(E + "/bulk-draft").get_json()
check("bulk draft: BCC list = exactly the low students; generic text without individual percentages",
      sorted(b["recipients"]) == ["s2@x.com", "s4@x.com"] and "33.3" not in b["body"] and "75%" in b["body"] and "Ms. Sharma" in b["body"])
check("email APIs need teacher login (student 403)", S[1].get(E + "/bulk-draft").status_code == 403 and S[1].post(E + "/send", json={}).status_code == 403 and S[1].get(E + "/status").status_code == 403)
check("draft logging records 'mailto_opened' only for low students of this teacher (ignores Amit, other teacher's Zed)",
      T1.post(E + "/opened", json={"student_ids": [2, 1, 5]}).get_json()["logged"] == 1 and q("SELECT kind, student_id FROM email_notifications") == [("mailto_opened", 2)])
check("invalid student list -> 400", T1.post(E + "/opened", json={"student_ids": ["x"]}).status_code == 400)

# ---------------------------------------------------------------- emails: real sending through SMTP
check("status: sending not configured by default", T1.get(E + "/status").get_json()["smtp_configured"] is False)
r = T1.post(E + "/send", json={}); check("send without SMTP -> 503 with a helpful message, nothing logged as sent", r.status_code == 503 and "draft" in r.get_json()["error"] and q("SELECT COUNT(*) FROM email_notifications WHERE kind='sent'")[0][0] == 0)
sink = SmtpSink()
config.SMTP_HOST, config.SMTP_PORT, config.SMTP_FROM, config.SMTP_USER, config.SMTP_TLS = "127.0.0.1", sink.port, "teacher@college.edu", "", "none"
check("status: configured once SMTP settings exist", T1.get(E + "/status").get_json()["smtp_configured"] is True)
r = T1.post(E + "/send", json={"student_ids": [2, 1, 5]}).get_json()
check("send to [Neha, Amit(not low), Zed(not yours)] -> only Neha is emailed", r["sent"] == ["Neha"] and r["failed"] == [])
check("the fake mail server really received 1 email", len(sink.messages) == 1)
m = sink.messages[0]; body = m.get_payload(decode=True).decode()
check("email: To s2@x.com, From teacher@college.edu, subject mentions 33.3%", (m["To"], m["From"]) == ("s2@x.com", "teacher@college.edu") and "33.3%" in m["Subject"])
check("email body is personal: Neha, 33.3%, 75%, Ms. Sharma", all(w in body for w in ("Dear Neha", "33.3%", "75%", "Ms. Sharma")))
check("no Bcc/Cc headers (other students' addresses never exposed)", m["Bcc"] is None and m["Cc"] is None)
check("send logged as 'sent' (and the earlier draft log is a different kind)", q("SELECT kind, student_id FROM email_notifications ORDER BY id") == [("mailto_opened", 2), ("sent", 2)])
r = T1.post(E + "/send", json={}).get_json()
check("send to ALL low students -> Neha and =EVIL() (2 emails, 3 total at server)", sorted(r["sent"]) == ["=EVIL()", "Neha"] and len(sink.messages) == 3)
check("emailing nobody is refused (400) when no student is selected/low", T1.post(E + "/send", json={"student_ids": [1]}).status_code == 400)
config.SMTP_PORT = 1      # nothing listens here -> every send fails
r = T1.post(E + "/send", json={"student_ids": [2]}); j = r.get_json()
check("SMTP failure is reported per student and NOT logged as sent", r.status_code == 200 and j["sent"] == [] and j["failed"][0]["name"] == "Neha"
      and q("SELECT COUNT(*) FROM email_notifications WHERE kind='sent'")[0][0] == 3)
config.SMTP_HOST = ""; sink.close()

# ---------------------------------------------------------------- student: own attendance
SA = "/api/student/attendance"
check("student attendance API: anon 401, teacher 403", app.test_client().get(SA).status_code == 401 and T1.get(SA).status_code == 403)
a = S[1].get(SA).get_json()
check("Amit: 3 of 4 = 75.0%, not low at 75", (a["present"], a["total"], a["percentage"], a["is_low"]) == (3, 4, 75.0, False))
sub = {x["subject"]: x for x in a["subjects"]}
check("subject-wise: DSA = P,P = 2/2 (100%); General = A,P = 1/2", (sub["DSA"]["present"], sub["DSA"]["total"], sub["DSA"]["percentage"]) == (2, 2, 100.0) and (sub["General"]["present"], sub["General"]["total"]) == (1, 2))
check("history: newest first, 4 rows, own records only", [h["session_id"] for h in a["history"]] == [s5, s3, s2, s1] and all(h["status"] in ("present", "absent") for h in a["history"]))
check("history row has date, subject, label, status", a["history"][0] == {**a["history"][0], "date": "2026-10-04", "subject": "General", "status": "present", "label": "Group: Lab Team"})
check("limit parameter works", len(S[1].get(SA + "?limit=2").get_json()["history"]) == 2)
n = S[2].get(SA).get_json(); check("Neha sees ONLY her own data (1/3 = 33.3%, low)", (n["present"], n["total"], n["percentage"], n["is_low"]) == (1, 3, 33.3, True) and len(n["history"]) == 3)
check("Rohan's attendance is only in his own view (1 record)", len(S[3].get(SA).get_json()["history"]) == 1 and S[3].get(SA).get_json()["subjects"][0]["subject"] == "Digital Logic")
check("another teacher's student sees nothing of teacher 1's sessions", [h["session_id"] for h in S[5].get(SA).get_json()["history"]] == [s7])
check("student with no records: percentage null, empty lists, not flagged low", (lambda r: (r["percentage"], r["subjects"], r["history"], r["is_low"]))(login("new@x.com", "student").get(SA).get_json()) == (None, [], [], False))
check("the waiting session never shows in a student's history", all(h["session_id"] != s6 for h in a["history"]))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
