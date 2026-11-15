"""Stage 9 tests: forgot password, join with class code, low-attendance alerts, Excel export.  Run from the project root: python tests/test_stage9.py"""
import io, os, sys, tempfile, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from openpyxl import load_workbook
from app import create_app
from services import emails, ratelimit, alerts

app = create_app(os.path.join(tempfile.mkdtemp(), "t.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp)
for em in ("t1@x.com", "t2@x.com"):
    u = c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,'teacher')", (em, generate_password_hash("secret123"))).lastrowid
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (u, em))
c.commit(); c.close()
def q(sql, *a):
    cn = sqlite3.connect(dbp); r = cn.execute(sql, a).fetchall(); cn.close(); return r
def login(email, pw, role):
    cl = app.test_client(); r = cl.post("/api/auth/login", json={"email": email, "password": pw, "role": role}); return cl, r
T1, _ = login("t1@x.com", "secret123", "teacher"); T2, _ = login("t2@x.com", "secret123", "teacher")
A = "/api/teacher"; ST = "/api/student"; P = f"{A}/sessions"
cid = T1.post(f"{A}/classes", json={"name": "DSA"}).get_json()["id"]
for n in ("A", "B"): T1.post(f"{A}/classes/{cid}/sections", json={"name": n})
secs = {s["name"]: s for s in [x for x in T1.get(f"{A}/classes").get_json()["classes"] if x["id"] == cid][0]["sections"]}
def add(sec, roll, name, email, pw="pass1234"):
    return T1.post(f"{A}/students", json={"roll_no": roll, "name": name, "email": email, "section_id": secs[sec]["id"], "password": pw})

# mail capture
sent = []; emails.SYNC = True
emails.send_one = lambda to, subj, body: sent.append((to, subj, body))

# ================= 1. forgot password
add("A", "1", "Asha", "asha@x.com")
check("no SMTP configured -> clear message (503), nothing sent", app.test_client().post("/api/auth/forgot", json={"email": "asha@x.com", "role": "student"}).status_code == 503
      and app.test_client().get("/api/auth/forgot-status").get_json()["email_enabled"] is False)
emails.smtp_configured = lambda: True
ratelimit.reset_all()
Z = app.test_client()
r = Z.post("/api/auth/forgot", json={"email": "asha@x.com", "role": "student"})
check("SMTP on: request accepted and a mail with a 6-digit code was sent", r.status_code == 200 and len(sent) == 1 and sent[0][0] == "asha@x.com")
code = [w for w in sent[0][2].split() if w.isdigit() and len(w) == 6][0]
r2 = Z.post("/api/auth/forgot", json={"email": "nobody@x.com", "role": "student"})
check("unknown email gets the SAME answer and no mail (cannot find out who is registered)", r2.status_code == 200 and r2.get_json() == r.get_json() and len(sent) == 1)
check("code is not stored in clear text in the database", code not in str(q("select * from password_resets")))
check("wrong code refused", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": "000000" if code != "000000" else "111111", "new_password": "brandnew1"}).status_code == 400)
check("code for the wrong ROLE does not work", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "teacher", "code": code, "new_password": "brandnew1"}).status_code == 400)
check("short new password refused", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": code, "new_password": "123"}).status_code == 400)
check("right code resets the password", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": code, "new_password": "brandnew1"}).status_code == 200
      and login("asha@x.com", "brandnew1", "student")[1].status_code == 200 and login("asha@x.com", "pass1234", "student")[1].status_code == 401)
check("a code works only once", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": code, "new_password": "again1234"}).status_code == 400)
# lock after 5 wrong tries
Z.post("/api/auth/forgot", json={"email": "asha@x.com", "role": "student"}); code2 = [w for w in sent[-1][2].split() if w.isdigit() and len(w) == 6][0]
wrong = "000000" if code2 != "000000" else "111111"
for _ in range(5): Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": wrong, "new_password": "xxxxxx"})
check("after 5 wrong tries even the RIGHT code is locked", Z.post("/api/auth/reset-password", json={"email": "asha@x.com", "role": "student", "code": code2, "new_password": "xxxxxx"}).status_code == 400)
# expiry
Z.post("/api/auth/forgot", json={"email": "t1@x.com", "role": "teacher"}); code3 = [w for w in sent[-1][2].split() if w.isdigit() and len(w) == 6][0]
cn = sqlite3.connect(dbp); cn.execute("UPDATE password_resets SET expires_at = 1"); cn.commit(); cn.close()
check("expired code refused", Z.post("/api/auth/reset-password", json={"email": "t1@x.com", "role": "teacher", "code": code3, "new_password": "newteach1"}).status_code == 400)
ratelimit.reset_all()
for i in range(3): rr = Z.post("/api/auth/forgot", json={"email": "asha@x.com", "role": "student"})
check("only 3 reset mails per hour per email (4th -> 429)", Z.post("/api/auth/forgot", json={"email": "asha@x.com", "role": "student"}).status_code == 429)
ratelimit.reset_all()
Z.post("/api/auth/forgot", json={"email": "t1@x.com", "role": "teacher"}); code4 = [w for w in sent[-1][2].split() if w.isdigit() and len(w) == 6][0]
check("teachers can reset their password the same way", Z.post("/api/auth/reset-password", json={"email": "t1@x.com", "role": "teacher", "code": code4, "new_password": "newteach1"}).status_code == 200
      and login("t1@x.com", "newteach1", "teacher")[1].status_code == 200)
T1, _ = login("t1@x.com", "newteach1", "teacher")

# teacher one-click reset of a student's password
sid_asha = q("select id from students where roll_no='1'")[0][0]
r = T1.post(f"{A}/students/{sid_asha}/reset-password")
check("teacher can give a student a new password (shown once)", r.status_code == 200 and login("asha@x.com", r.get_json()["password"], "student")[1].status_code == 200)
check("other teacher cannot (404), student cannot (403)", T2.post(f"{A}/students/{sid_asha}/reset-password").status_code == 404 and login("asha@x.com", r.get_json()["password"], "student")[0].post(f"{A}/students/{sid_asha}/reset-password").status_code == 403)

# ================= 2. join with class code
ratelimit.reset_all()
sa = secs["A"]["id"]
check("codes are off by default", T1.get(f"{A}/classes").get_json()["classes"][0]["sections"][0]["join_mode"] == "off")
check("bad mode refused / other teacher cannot touch my section", T1.put(f"{A}/join/sections/{sa}", json={"mode": "x"}).status_code == 400 and T2.put(f"{A}/join/sections/{sa}", json={"mode": "open"}).status_code == 404)
check("a code that is switched off cannot be used", app.test_client().post("/api/join/preview", json={"code": "ABCD2345"}).status_code == 404)
r = T1.put(f"{A}/join/sections/{sa}", json={"mode": "open"}).get_json(); code_a = r["join_code"].replace("-", "")
check("switching on makes an 8-character code", r["join_mode"] == "open" and len(code_a) == 8)
J = app.test_client()
pv = J.post("/api/join/preview", json={"code": r["join_code"].lower()})
check("preview shows class + section + teacher (code is case/hyphen tolerant)", pv.status_code == 200 and pv.get_json()["class_name"] == "DSA" and pv.get_json()["section_name"] == "A")
body = {"code": code_a, "name": "Neha", "roll_no": "5", "email": "neha@x.com", "password": "nehapass1", "phone": ""}
r = J.post("/api/join/signup", json=body)
check("open code: new student creates a login and is joined + logged in at once (201)", r.status_code == 201 and J.get(f"{ST}/profile").status_code == 200)
check("the new student is in section A with the right roll", q("select roll_no, section_id from students where name='Neha'") == [("5", sa)])
check("same email again -> 409 (log in and use Join a class)", app.test_client().post("/api/join/signup", json={**body, "roll_no": "6"}).status_code == 409)
check("roll number already used in that section -> 409", app.test_client().post("/api/join/signup", json={**body, "email": "z@x.com"}).status_code == 409)
check("short password / bad email refused", app.test_client().post("/api/join/signup", json={**body, "email": "q@x.com", "roll_no": "7", "password": "123"}).status_code == 400
      and app.test_client().post("/api/join/signup", json={**body, "email": "nope", "roll_no": "7"}).status_code == 400)
# existing student joins a second section while logged in
pwd = T1.post(f"{A}/students/{sid_asha}/reset-password").get_json()["password"]; S_asha, _ = login("asha@x.com", pwd, "student")
rb = T1.put(f"{A}/join/sections/{secs['B']['id']}", json={"mode": "approval"}).get_json(); code_b = rb["join_code"].replace("-", "")
r = S_asha.post(f"{ST}/join", json={"code": code_b, "roll_no": "1"})
check("logged-in student asks to join section B (approval mode) -> 202 pending", r.status_code == 202 and r.get_json()["status"] == "pending")
check("asking twice is refused", S_asha.post(f"{ST}/join", json={"code": code_b, "roll_no": "1"}).status_code == 409)
check("she is NOT in B yet", q("select count(*) from students where user_id=(select user_id from students where roll_no='1' and section_id=?) ", sa)[0][0] == 1)
r = app.test_client().post("/api/join/signup", json={"code": code_b, "name": "Omar", "roll_no": "9", "email": "omar@x.com", "password": "omarpass1"})
check("new signup in approval mode -> 202 pending, NO login yet", r.status_code == 202 and login("omar@x.com", "omarpass1", "student")[1].status_code == 401)
rq = T1.get(f"{A}/join/requests").get_json()
check("teacher sees 2 pending requests", rq["count"] == 2 and {x["name"] for x in rq["requests"]} == {"Asha", "Omar"})
check("other teacher sees none and cannot approve (404)", T2.get(f"{A}/join/requests").get_json()["count"] == 0 and T2.post(f"{A}/join/requests/{rq['requests'][0]['id']}/approve").status_code == 404)
for x in rq["requests"]:
    assert T1.post(f"{A}/join/requests/{x['id']}/approve").status_code == 200
check("approved: Omar can now log in, Asha is in both sections", login("omar@x.com", "omarpass1", "student")[1].status_code == 200
      and q("select count(*) from students where user_id=(select user_id from students where roll_no='1' and section_id=?)", sa)[0][0] == 2)
nt = S_asha.get(f"{ST}/notifications").get_json()
check("Asha got an 'approved' notification on her dashboard", any("approved" in n["message"] for n in nt["notifications"]) and nt["unread"] >= 1)
S_asha.post(f"{ST}/notifications/read"); check("notifications can be marked read", S_asha.get(f"{ST}/notifications").get_json()["unread"] == 0)
r = app.test_client().post("/api/join/signup", json={"code": code_b, "name": "Rej", "roll_no": "10", "email": "rej@x.com", "password": "rejpass12"})
rid = T1.get(f"{A}/join/requests").get_json()["requests"][0]["id"]
check("reject removes the request and creates no login", T1.post(f"{A}/join/requests/{rid}/reject").status_code == 200 and not q("select 1 from users where email='rej@x.com'"))
check("new code kills the old one at once", T1.put(f"{A}/join/sections/{sa}", json={"regenerate": True}).get_json()["join_code"].replace("-", "") != code_a
      and app.test_client().post("/api/join/preview", json={"code": code_a}).status_code == 404)
ratelimit.reset_all(); G = app.test_client()
codes = [G.post("/api/join/preview", json={"code": "ZZZZ%04d" % i}).status_code for i in range(31)]
check("guessing codes is rate-limited (429 after 30 tries)", codes[-1] == 429 and 404 in codes)
ratelimit.reset_all()
check("deleting a student that has a login keeps nothing dangling (cascade)", q("select count(*) from join_requests")[0][0] == 0)

# ================= 3. low-attendance alerts
ratelimit.reset_all()
add("A", "20", "Low", "low@x.com"); sent.clear()
def run_session(sec):
    sid = T1.post(P, json={"type": "normal", "section_id": secs[sec]["id"]}).get_json()["id"]; T1.post(f"{P}/{sid}/start"); T1.post(f"{P}/{sid}/end"); return sid
run_session("A")
low_uid = q("select user_id from students where roll_no='20'")[0][0]
n = q("select message from notifications where user_id=? and kind='low_attendance'", low_uid)
check("session ended: absent student gets an in-app low-attendance notice (0% < 75%)", len(n) == 1 and "0%" in n[0][0] and "DSA - A" in n[0][0])
check("auto-email is OFF by default -> no mail sent", not [m for m in sent if m[0] == "low@x.com"])
run_session("A")
check("second session within a week: no second notice (cooldown)", len(q("select 1 from notifications where user_id=? and kind='low_attendance'", low_uid)) == 1)
T1.put(f"{A}/settings", json={"name": "T", "phone": "", "warning_threshold": 75, "session_minutes": 10, "auto_alerts": True, "weekly_summary": True})
cn = sqlite3.connect(dbp); cn.execute("DELETE FROM alert_log"); cn.commit(); cn.close()
run_session("A")
check("with 'email students' ON an email is sent too", any(m[0] == "low@x.com" and "below" in m[2] for m in sent))
st = T1.get(f"{A}/settings").get_json()
check("settings return the two toggles + smtp flag", st["auto_alerts"] is True and st["weekly_summary"] is True and st["smtp_configured"] is True)
sent.clear(); check("'email me the summary now' works and lists the low students", T1.post(f"{A}/settings/send-summary").status_code == 200 and sent and "Low (20)" in sent[-1][2])
sent.clear(); cn = sqlite3.connect(dbp); cn.row_factory = sqlite3.Row
check("weekly tick skips a teacher who just got one", alerts.weekly_tick(cn) == 0 and not sent)
cn.execute("UPDATE teachers SET last_summary_at = datetime('now','-8 days') WHERE weekly_summary=1"); cn.commit()
check("weekly tick sends to a teacher who is due", alerts.weekly_tick(cn) == 1 and sent); cn.close()
emails.smtp_configured = lambda: False
check("no SMTP: summary refused (503) but in-app alerts keep working", T1.post(f"{A}/settings/send-summary").status_code == 503)
emails.smtp_configured = lambda: True

# ================= 4. Excel export
r = T1.get(f"{A}/reports/export.xlsx")
wb = load_workbook(io.BytesIO(r.data))
check("xlsx report downloads as a real workbook", r.status_code == 200 and "spreadsheetml" in r.mimetype)
check("sheets: Summary, Below 75%, then one per section", wb.sheetnames[:2] == ["Summary", "Below 75%"] and "DSA A" in wb.sheetnames and "DSA B" in wb.sheetnames)
ws = wb["DSA A"]; head = [c.value for c in ws[1]]
check("section sheet has roll/name/email/percentage/status columns", head[:7] == ["Roll No", "Name", "Email", "Present", "Total sessions", "Attendance %", "Status"])
rows = {r_[0].value: r_ for r_ in ws.iter_rows(min_row=2)}
check("a low student is marked LOW with 0 %", rows["20"][6].value == "LOW" and rows["20"][5].value == 0)
T1.put(f"{A}/students/{sid_asha}", json={"roll_no": "1", "name": "=HYPERLINK(\"http://evil\")", "email": "asha@x.com", "section_id": secs["A"]["id"], "password": ""})
wb = load_workbook(io.BytesIO(T1.get(f"{A}/reports/export.xlsx").data)); vals = [r_[1].value for r_ in wb["DSA A"].iter_rows(min_row=2)]
check("a name starting with '=' is stored as text, not a formula", any(v and v.startswith("'=") for v in vals) and all(c.data_type != "f" for r_ in wb["DSA A"].iter_rows() for c in r_))
sid = q("select id from attendance_sessions order by id limit 1")[0][0]
r = T1.get(f"{A}/history/{sid}.xlsx"); wb2 = load_workbook(io.BytesIO(r.data))
check("session xlsx has one sheet per section", r.status_code == 200 and wb2.sheetnames == ["DSA - A"])
check("xlsx exports need a teacher login (401) and own data (404)", app.test_client().get(f"{A}/reports/export.xlsx").status_code == 401 and T2.get(f"{A}/history/{sid}.xlsx").status_code == 404
      and login("omar@x.com", "omarpass1", "student")[0].get(f"{A}/reports/export.xlsx").status_code == 403)

# ================= 5. upgrade of an old database
old = os.path.join(tempfile.mkdtemp(), "old.db"); c = sqlite3.connect(old)
c.executescript(open("/home/claude/orig/quickmark/backend/database/schema.sql").read()); c.commit(); c.close()
from database import db as D
D.init_db(old); D.init_db(old)
c = sqlite3.connect(old)
cols = lambda t: {r[1] for r in c.execute(f"pragma table_info({t})")}
check("old database gains the new columns and tables safely (twice)", {"join_code", "join_mode"} <= cols("sections") and {"auto_alerts", "weekly_summary"} <= cols("teachers")
      and {"password_resets", "join_requests", "notifications", "alert_log"} <= {r[0] for r in c.execute("select name from sqlite_master where type='table'")})

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
