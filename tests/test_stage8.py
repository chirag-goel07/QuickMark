"""Stage 8 tests: same roll no in different sections, one student in several classes, bulk import,
first-login password change, section-wise editing after a session. Run from the project root:  python tests/test_stage8.py"""
import os, sys, tempfile, sqlite3, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app

app = create_app(os.path.join(tempfile.mkdtemp(), "t.db"))
dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
for em in ("t1@x.com", "t2@x.com"):
    u = c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,'teacher')", (em, generate_password_hash("secret123"))).lastrowid
    c.execute("INSERT INTO teachers(user_id,name) VALUES(?,?)", (u, em))
c.commit(); c.close()

def login(email, pw, role):
    cl = app.test_client(); r = cl.post("/api/auth/login", json={"email": email, "password": pw, "role": role}); return cl, r
T1, _ = login("t1@x.com", "secret123", "teacher"); T2, _ = login("t2@x.com", "secret123", "teacher")
A = "/api/teacher"
def mkclass(cl, name, secs):
    cid = cl.post(f"{A}/classes", json={"name": name}).get_json()["id"]
    for s in secs: cl.post(f"{A}/classes/{cid}/sections", json={"name": s})
    return {s["name"]: s["id"] for s in [x for x in cl.get(f"{A}/classes").get_json()["classes"] if x["id"] == cid][0]["sections"]}, cid
dsa, dsa_id = mkclass(T1, "DSA", ["ML1", "ML2"]); oops, _ = mkclass(T1, "OOPS", ["A"]); other, _ = mkclass(T2, "Maths", ["X"])
def add(cl, sec, roll, name, email, pw="pass1234", **kw):
    return cl.post(f"{A}/students", json={"roll_no": roll, "name": name, "email": email, "section_id": sec, "password": pw, **kw})

# ---- 1. same roll no in different sections
r1 = add(T1, dsa["ML1"], "1", "Asha", "asha@x.com"); r2 = add(T1, dsa["ML2"], "1", "Bina", "bina@x.com")
check("same roll number in two different sections is allowed (201)", r1.status_code == 201 and r2.status_code == 201)
r = add(T1, dsa["ML1"], "1", "Clone", "clone@x.com")
check("same roll number twice in the SAME section is refused (409, says which section)", r.status_code == 409 and "DSA - ML1" in r.get_json()["error"])

# ---- 2. same student in two classes (DSA + OOPS)
r = add(T1, oops["A"], "7", "Asha", "asha@x.com", pw="")
check("same email in a second class: added as the same person (201, 'enrolled')", r.status_code == 201 and r.get_json()["status"] == "enrolled")
check("their password was NOT changed by the second add", login("asha@x.com", "pass1234", "student")[1].status_code == 200)
r = add(T1, dsa["ML1"], "9", "Asha again", "asha@x.com")
check("same email twice in the SAME section refused (409)", r.status_code == 409)
check("a teacher's email cannot be enrolled as a student (409)", add(T1, dsa["ML1"], "10", "X", "t2@x.com").status_code == 409)
S, _ = login("asha@x.com", "pass1234", "student")
cl = S.get("/api/student/classes").get_json()["classes"]
check("student sees BOTH classes", sorted(x["class_name"] for x in cl) == ["DSA", "OOPS"])
check("one login, one face/picture slot for all classes (profile lists both enrollments)", len(S.get("/api/student/profile").get_json()["enrollments"]) == 2)
# other teacher can also take the same person
r = add(T2, other["X"], "55", "Asha", "asha@x.com", pw="")
check("a second TEACHER can add the same email too, still no password change", r.status_code == 201 and login("asha@x.com", "pass1234", "student")[1].status_code == 200)
e = T1.put(f"{A}/students/{r1.get_json()['id']}", json={"roll_no": "1", "name": "Asha", "email": "asha@x.com", "section_id": dsa["ML1"], "password": "hacked99"})
check("teacher cannot overwrite the password of a person who is also in another teacher's class (403)", e.status_code == 403 and login("asha@x.com", "pass1234", "student")[1].status_code == 200)

# ---- 3. delete only removes THIS enrollment
oops_sid = [s for s in T1.get(f"{A}/students").get_json()["students"] if s["class_name"] == "OOPS"][0]["id"]
check("deleting the OOPS enrollment keeps the DSA one and the login", T1.delete(f"{A}/students/{oops_sid}").status_code == 200
      and [x["class_name"] for x in S.get("/api/student/classes").get_json()["classes"]] == ["DSA", "Maths"] and S.get("/api/auth/me").status_code == 200)

# ---- 4. sessions for a student in several classes: join + scan + request pick the right enrollment
add(T1, oops["A"], "7", "Asha", "asha@x.com", pw="")
add(T1, dsa["ML1"], "2", "Chirag", "chirag@x.com"); add(T1, dsa["ML2"], "2", "Dev", "dev@x.com")
P = f"{A}/sessions"; ST = "/api/student"
sid = T1.post(P, json={"type": "normal", "section_id": oops["A"]}).get_json()["id"]
act = S.get(f"{ST}/sessions/active").get_json()["sessions"]
check("student sees the OOPS session among her open sessions", [x["id"] for x in act] == [sid])
check("join OOPS session (picks the OOPS enrollment)", S.post(f"{ST}/sessions/{sid}/join").status_code == 200)
T1.post(f"{P}/{sid}/start"); tok = sqlite3.connect(dbp).execute("SELECT token FROM qr_tokens ORDER BY expires_at DESC LIMIT 1").fetchone()[0]
check("scan marks her present in OOPS", S.post(f"{ST}/attendance/scan", json={"token": tok}).status_code == 200)
st = T1.get(f"{P}/{sid}").get_json()
check("running session: no manual-mark list, /mark refused (409)", "not_present_students" not in st and T1.post(f"{P}/{sid}/mark", json={"student_id": 1, "status": "present"}).status_code == 409)
T1.post(f"{P}/{sid}/end")
att = S.get(f"{ST}/attendance").get_json()
check("student's attendance counts the OOPS session only (1 of 1)", (att["present"], att["total"]) == (1, 1))

# ---- 5. section-wise edit boxes after a GROUP session across ML1 + ML2
students = T1.get(f"{A}/students").get_json()["students"]
ids = [s["id"] for s in students if s["class_name"] == "DSA"]
gid = T1.post(f"{A}/groups", json={"name": "Lab", "student_ids": ids}).get_json()["id"]
gs = T1.post(P, json={"type": "group", "group_id": gid}).get_json()["id"]; T1.post(f"{P}/{gs}/start"); T1.post(f"{P}/{gs}/end")
d = T1.get(f"{A}/history/{gs}").get_json()
check("ended session detail has one box per section (ML1, ML2)", sorted(b["label"] for b in d["sections"]) == ["DSA - ML1", "DSA - ML2"])
box = {b["label"]: b for b in d["sections"]}
check("each box only lists its own section's students", {s["name"] for s in box["DSA - ML1"]["students"]} == {"Asha", "Chirag"} and {s["name"] for s in box["DSA - ML2"]["students"]} == {"Bina", "Dev"})
dev = [s for s in box["DSA - ML2"]["students"] if s["name"] == "Dev"][0]["id"]
r = T1.put(f"{A}/history/{gs}/records", json={"student_id": dev, "status": "present"})
check("editing after the session works and the ML2 box updates", r.status_code == 200 and {b["label"]: b["present"] for b in r.get_json()["sections"]}["DSA - ML2"] == 1)

# ---- 6. first password set by teacher -> student must change it
add(T1, dsa["ML1"], "20", "Eve", "eve@x.com", pw="first123")
E, _ = login("eve@x.com", "first123", "student")
check("login with the teacher's password works and the student can change it later", E.get("/api/auth/me").get_json()["must_change_password"] is True)
check("changing to the same password is refused", E.post(f"{ST}/password", json={"current_password": "first123", "new_password": "first123"}).status_code == 400)
check("student changes the password (200) and the flag clears", E.post(f"{ST}/password", json={"current_password": "first123", "new_password": "mine4567"}).status_code == 200
      and E.get("/api/auth/me").get_json()["must_change_password"] is False)
check("old password stops working, new one works", login("eve@x.com", "first123", "student")[1].status_code == 401 and login("eve@x.com", "mine4567", "student")[1].status_code == 200)
r = add(T1, dsa["ML1"], "21", "Gen", "gen@x.com", pw="")
gp = r.get_json().get("generated_password")
check("blank password -> a random one is generated and returned once", gp and len(gp) >= 8 and login("gen@x.com", gp, "student")[1].status_code == 200)

# ---- 7. bulk import
rows = [{"roll_no": "30", "name": "B1", "email": "b1@x.com"}, {"roll_no": "31", "name": "B2", "email": "B2@x.com", "phone": "123"},
        {"roll_no": "30", "name": "Dup roll", "email": "b3@x.com"},                 # roll used twice in the batch
        {"roll_no": "32", "name": "Bad email", "email": "nope"},
        {"roll_no": "33", "name": "Chirag", "email": "chirag@x.com"},               # in DSA-ML1 already, now also ML2 -> enrolled
        {"roll_no": "34", "name": "Asha", "email": "asha@x.com"},                   # existing login, other section -> enrolled
        
        {"roll_no": "", "name": "No roll", "email": "n@x.com"}]
r = T1.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "default_password": "College1", "rows": rows})
j = r.get_json(); by = {x["row"]: x for x in j["results"]}
check("bulk: counts are 2 created, 2 linked, 3 skipped", r.status_code == 200 and (j["created"], j["enrolled"], j["failed"]) == (2, 2, 3))
check("bulk: duplicate roll inside the batch, bad email, missing roll and double-enrolment are skipped with reasons",
      all(by[i]["status"] == "error" and by[i]["message"] for i in (3, 4, 7)))
r_again = T1.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "rows": [rows[0]]}).get_json()["results"][0]
check("bulk: importing the same row twice is refused (already in the section)", r_again["status"] == "error")
check("bulk: common first password works and forces a change", login("b1@x.com", "College1", "student")[0].get("/api/auth/me").get_json()["must_change_password"] is True)
check("bulk: existing login was linked, password untouched", by[5]["status"] == "enrolled" and by[6]["status"] == "enrolled" and login("asha@x.com", "pass1234", "student")[1].status_code == 200)
r = T1.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "rows": [{"roll_no": "40", "name": "R", "email": "r40@x.com"}]}).get_json()
check("bulk without a password: random password returned and valid", login("r40@x.com", r["results"][0]["password"], "student")[1].status_code == 200)
check("bulk: other teacher's section refused (400)", T2.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "rows": rows}).status_code == 400)
check("bulk: empty / too many rows refused", T1.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "rows": []}).status_code == 400
      and T1.post(f"{A}/students/bulk", json={"section_id": dsa["ML2"], "rows": [{}] * 501}).status_code == 400)
check("bulk: students cannot use it (403) / anonymous (401)", S.post(f"{A}/students/bulk", json={}).status_code == 403 and app.test_client().post(f"{A}/students/bulk", json={}).status_code == 401)
check("CSV template downloads", "roll_no,name,email" in T1.get(f"{A}/students/template.csv").get_data(as_text=True))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
