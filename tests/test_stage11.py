"""Stage 11 tests: the profile picture is taken from the FIRST face scan and students cannot change it.
Run from the project root:  python tests/test_stage11.py   (temporary database only)"""
import base64, os, random, sqlite3, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from werkzeug.security import generate_password_hash
from app import create_app

app = create_app(os.path.join(tempfile.mkdtemp(), "t11.db")); dbp = app.config["DATABASE_PATH"]
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name)

c = sqlite3.connect(dbp); c.execute("PRAGMA foreign_keys=ON")
def user(email, role): return c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)", (email, generate_password_hash("secret123"), role)).lastrowid
for em, nm in [("t1@x.com", "T One"), ("t2@x.com", "T Two")]:
    c.execute("INSERT INTO teachers(user_id,name,require_face) VALUES(?,?,1)", (user(em, "teacher"), nm))
c.execute("INSERT INTO classes(teacher_id,name) VALUES(1,'CS')"); c.execute("INSERT INTO sections(class_id,name) VALUES(1,'A')")
for i in (1, 2, 3):
    c.execute("INSERT INTO students(user_id,roll_no,name,section_id) VALUES(?,?,?,1)", (user(f"s{i}@x.com", "student"), f"R{i}", f"Student{i}"))
c.commit(); c.close()

def login(email, role): cl = app.test_client(); cl.post("/api/auth/login", json={"email": email, "password": "secret123", "role": role}); return cl
T1, T2 = login("t1@x.com", "teacher"), login("t2@x.com", "teacher")
S = {i: login(f"s{i}@x.com", "student") for i in (1, 2, 3)}
ST = "/api/student"
rng = random.Random(5)
def jpeg(seed): r = random.Random(seed); return b"\xff\xd8\xff\xe0" + bytes(r.randrange(256) for _ in range(1500)) + b"\xff\xd9"
b64 = lambda b: base64.b64encode(b).decode()
def samples():
    base = [rng.uniform(-.5, .5) for _ in range(128)]
    return [[x + rng.uniform(-.01, .01) for x in base] for _ in range(3)]
enroll = lambda i, photo="__none__", sm=None: S[i].post(f"{ST}/face/enroll", json={"samples": sm or samples(), **({} if photo == "__none__" else {"photo": photo})})
q = lambda sql, *a: (lambda cc: (cc.execute(sql, a).fetchall(), cc.close())[0])(sqlite3.connect(dbp))

check("before setup: no picture, not enrolled", S[1].get(f"{ST}/avatar").status_code == 404 and S[1].get(f"{ST}/profile").get_json()["face_enrolled"] is False)

# ---- invalid photos are refused and nothing is half-saved
bad = {"not base64": "!!!notbase64!!!", "PNG bytes": b64(b"\x89PNG\r\n\x1a\n" + b"x" * 200), "text pretending to be a JPEG": b64(b"<script>alert(1)</script>"),
       "JPEG without end marker": b64(b"\xff\xd8\xff" + b"x" * 100), "201 KB photo": b64(b"\xff\xd8\xff" + b"x" * (201 * 1024) + b"\xff\xd9"), "empty": ""}
for name, val in bad.items():
    r = enroll(2, val)
    check(f"refused: {name} (400)", r.status_code == 400)
check("after the refusals student 2 is still not enrolled and has no picture", q("SELECT face_descriptor IS NULL, avatar IS NULL FROM students WHERE id = 2") == [(1, 1)])

# ---- first scan: the photo becomes the profile picture automatically
P1 = jpeg(1)
r = enroll(1, b64(P1)); check("first face setup with a photo works (200)", r.status_code == 200)
g = S[1].get(f"{ST}/avatar")
check("the profile picture is exactly the photo from the scan", g.status_code == 200 and g.data == P1 and g.mimetype == "image/jpeg")
check("profile and /auth/me say: enrolled + has a picture", S[1].get(f"{ST}/profile").get_json()["has_avatar"] is True and S[1].get("/api/auth/me").get_json()["has_avatar"] is True
      and S[1].get(f"{ST}/profile").get_json()["face_enrolled"] is True)
check("the teacher sees the picture of their student; another teacher cannot", T1.get("/api/teacher/students/1/avatar").data == P1 and T2.get("/api/teacher/students/1/avatar").status_code == 404)

# ---- the student has NO way to change it
check("uploading a picture is refused (403) and the picture is unchanged", S[1].post(f"{ST}/avatar", data=jpeg(9), content_type="image/jpeg").status_code == 403 and S[1].get(f"{ST}/avatar").data == P1)
check("removing the picture is refused (403) and it stays", S[1].delete(f"{ST}/avatar").status_code == 403 and S[1].get(f"{ST}/avatar").data == P1)
r = S[1].post(f"{ST}/avatar", data=jpeg(9), content_type="image/jpeg")
check("the refusal explains why", "face setup" in r.get_json()["error"] and "reset" in r.get_json()["error"])
r = enroll(1, b64(jpeg(2)))
check("a second face setup (e.g. with a fake face) is refused (409) and the picture is unchanged", r.status_code == 409 and S[1].get(f"{ST}/avatar").data == P1)
check("the teacher's student list shows the picture exists", {s["roll_no"]: s["has_avatar"] for s in T1.get("/api/teacher/students").get_json()["students"]} == {"R1": True, "R2": False, "R3": False})

# ---- a setup without a photo works, but the student still cannot add one later
check("setup without a photo still works (no picture)", enroll(3).status_code == 200 and S[3].get(f"{ST}/avatar").status_code == 404)
check("student 3 cannot add a picture afterwards (403)", S[3].post(f"{ST}/avatar", data=P1, content_type="image/jpeg").status_code == 403 and S[3].get(f"{ST}/avatar").status_code == 404)

# ---- only the teacher's face reset allows a new picture
check("another teacher cannot reset the face (404)", T2.post("/api/teacher/students/1/reset-face").status_code == 404 and S[1].get(f"{ST}/avatar").data == P1)
check("a student cannot reset their own face (403)", S[1].post("/api/teacher/students/1/reset-face").status_code == 403 and S[1].get(f"{ST}/avatar").data == P1)
check("teacher resets the face (200)", T1.post("/api/teacher/students/1/reset-face").status_code == 200)
check("reset removes the face AND the picture", S[1].get(f"{ST}/avatar").status_code == 404 and q("SELECT face_descriptor IS NULL, avatar IS NULL FROM students WHERE id = 1") == [(1, 1)])
P2 = jpeg(3); check("the new face setup takes a NEW picture", enroll(1, b64(P2)).status_code == 200 and S[1].get(f"{ST}/avatar").data == P2)
check("the avatar is never inside any JSON response", "\\u00ff" not in S[1].get(f"{ST}/profile").get_data(as_text=True) and b64(P2)[:20] not in S[1].get(f"{ST}/profile").get_data(as_text=True))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
