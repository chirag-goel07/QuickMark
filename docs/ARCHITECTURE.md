# QuickMark - Architecture, Database and API

## 1. Architecture (why it is built this way)
```
 Teacher laptop (browser)        Student phone/laptop (browser)
        |   HTTPS (REST + Socket.IO)      |
        +---------------+-----------------+
                        |
                 Flask server  (backend/app.py)
        routes/  -> services/  -> database/ (SQLite file)
                        |
        background task: every 3 s makes a new QR token and pushes it to the teacher screen
```
- **One server, one database.** Teacher and student sites are just web pages that talk to the same Flask server, so
  they work on different devices. Nothing important is stored in the browser.
- **Flask + SQLite** because they install with `pip` only, need no database server, and are easy to explain.
- **REST (JSON over HTTP)** for normal actions; **Socket.IO (WebSockets)** for live updates: waiting-room counts,
  the rotating QR, requests, and "the teacher started" messages.
- **Server decides everything.** Percentages, QR validity, expiry, duplicate checks, eligibility and face matching are
  all calculated/checked on the server; the browser only displays and sends raw input.
- **Layers:** `routes/` (HTTP, login/role checks) -> `services/` (the rules: sessions, face, emails, reports) -> `database/`.

### C++ core
The OOP/DSA logic is C++17 (`backend/cpp/`): sliding-window rate limiter, face-descriptor maths and wrong-face lock-out, attendance percentage / advice /
stable and natural sorting / streak, and the CSV writer with spreadsheet-formula protection. `backend/build_cpp.py` compiles it to a shared library
(`.so` / `.dll` / `.dylib`), `backend/services/core.py` loads it with `ctypes`. The rest of the backend (Flask routes, SQLite, sessions, QR tokens, e-mail,
Socket.IO) and the whole frontend are unchanged. Tests: `tests/test_cpp_core.py` and `python backend/build_cpp.py --test`.

## 2. Attendance session life cycle
`waiting` (waiting room, **no QR exists**) -> teacher presses START -> `active` (server makes a new token every 3 s;
a token is accepted for 5 s) -> teacher presses End, or the duration runs out -> `ended` (everyone who did not scan is saved
as absent). Normal (section) and group attendance use exactly the same code.

How a student gets marked present: (1) joins the waiting room (with a face check if the teacher requires it),
(2) scans the QR, **or** (3) the teacher accepts the student's request - sent **after the session ended**, within 7 days (`QUICKMARK_REQUEST_DAYS`;
in-session requests can be switched on with `QUICKMARK_REQUESTS_DURING_SESSION=1`), **or** (4) the teacher marks/edits manually.
Every manual change (teacher edit or accepted request) is stored in `attendance_edits` and each record remembers
how it was made (`marked_via` = qr / teacher / request).

## 3. Face verification (what it does and does not do)
- The browser (face-api, bundled, works offline) turns the camera picture into **128 numbers**. Only those numbers are sent.
  Attendance scans never upload a photo; the only picture sent is ONE small cropped photo at the first set-up, which becomes the profile picture (students cannot change it; a teacher's *Reset face* removes it). The server compares them with the student's enrolled numbers (distance <= 0.5).
- Enrollment happens once, **right after the student's first login** (3 captures that must look like the same person), never in the middle of a session. Only the teacher can reset it.
- 5 wrong faces within a minute lock that student out for a short time (stops guessing); they can still send a request.
- **Limits (be honest in your report):** there is no liveness detection, so a photo of the student held to the camera could
  pass; and a student could enroll someone else's face at first use. Reduce the risk by letting students enroll while
  you are present, resetting faces when in doubt, and watching the room. It is a deterrent against casual proxy
  attendance, not a security guarantee. Tell students what is stored and let them ask for it to be removed (Reset face).

## 4. Database tables
| Table | Purpose |
|---|---|
| `users` | Login accounts (email, password hash, role teacher/student) |
| `teachers` | Teacher profile + settings (warning threshold, default duration, require face) |
| `classes`, `sections`, `subjects` | Class -> sections and subjects (unique names per parent) |
| `students` | Student profile, section, the optional face template (128 numbers) and the small profile picture taken at the first face set-up (JPEG, max 200 KB) |
| `groups`, `group_members` | Custom groups of students for group attendance |
| `attendance_sessions` | One row per session (type normal/group, status, times, duration, totals) |
| `session_participants` | Who joined the waiting room (`PRIMARY KEY (session, student)` = no double join) |
| `qr_tokens` | The short-lived QR tokens with their expiry time |
| `attendance_records` | Present/absent per student per session (`PRIMARY KEY (session, student)` = no duplicates) |
| `attendance_requests` | Student requests to be marked present (one per student per session) |
| `attendance_edits` | Audit log of every manual change |
| `email_notifications` | Log of warning emails (draft opened vs really sent) |

Duplicate attendance is blocked **by the database itself** (primary keys), so even simultaneous scans cannot create two rows.
Old databases are upgraded automatically when the server starts (`database/db.py`).

## 5. Security measures
- Passwords are hashed (werkzeug). Login cookies are signed with a per-installation random key (`backend/secret.key`),
  are HttpOnly, SameSite=Lax, and `Secure` when HTTPS is on.
- Every API checks login **and** role; teachers can only touch their own classes/students/sessions (ownership checks);
  students can only read their own records. The user id always comes from the server-side session, never from the request.
- Profile pictures come only from the first face set-up (students have no upload/remove: `POST`/`DELETE /api/student/avatar` answer 403), are accepted only as small JPEGs (size and file markers checked on the server), served with `nosniff` and a locked-down CSP, and only to the student themselves or their own teacher.
- All SQL uses parameters; all text shown in pages is escaped; CSV exports neutralise spreadsheet formulas.
- Email passwords live only in server environment variables.
- Known limits: no login rate-limit (use a trusted network), self-signed HTTPS certificate, SQLite is meant for one college server.

## 6. API list (generated from the code)
| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login` | anyone |
| POST | `/api/auth/logout` | anyone |
| GET | `/api/auth/me` | anyone |
| GET | `/api/teacher/classes` | teacher |
| POST | `/api/teacher/classes` | teacher |
| DELETE | `/api/teacher/classes/{class_id}` | teacher |
| PUT | `/api/teacher/classes/{class_id}` | teacher |
| POST | `/api/teacher/classes/{class_id}/sections` | teacher |
| POST | `/api/teacher/classes/{class_id}/subjects` | teacher |
| GET | `/api/teacher/dashboard` | teacher |
| GET | `/api/teacher/emails/bulk-draft` | teacher |
| POST | `/api/teacher/emails/opened` | teacher |
| POST | `/api/teacher/emails/send` | teacher |
| GET | `/api/teacher/emails/status` | teacher |
| GET | `/api/teacher/groups` | teacher |
| POST | `/api/teacher/groups` | teacher |
| DELETE | `/api/teacher/groups/{group_id}` | teacher |
| GET | `/api/teacher/groups/{group_id}` | teacher |
| PUT | `/api/teacher/groups/{group_id}` | teacher |
| GET | `/api/teacher/history` | teacher |
| GET | `/api/teacher/history/export.csv` | teacher |
| GET | `/api/teacher/history/{session_id}` | teacher |
| GET | `/api/teacher/history/{session_id}.csv` | teacher |
| PUT | `/api/teacher/history/{session_id}/records` | teacher |
| GET | `/api/teacher/reports` | teacher |
| GET | `/api/teacher/reports/export.csv` | teacher |
| DELETE | `/api/teacher/sections/{section_id}` | teacher |
| PUT | `/api/teacher/sections/{section_id}` | teacher |
| POST | `/api/teacher/sessions` | teacher |
| GET | `/api/teacher/sessions/current` | teacher |
| POST | `/api/teacher/sessions/requests/{request_id}/accept` | teacher |
| POST | `/api/teacher/sessions/requests/{request_id}/reject` | teacher |
| GET | `/api/teacher/sessions/{session_id}` | teacher |
| POST | `/api/teacher/sessions/{session_id}/cancel` | teacher |
| POST | `/api/teacher/sessions/{session_id}/end` | teacher |
| POST | `/api/teacher/sessions/{session_id}/mark` | teacher |
| POST | `/api/teacher/sessions/{session_id}/start` | teacher |
| GET | `/api/teacher/settings` | teacher |
| PUT | `/api/teacher/settings` | teacher |
| POST | `/api/teacher/settings/password` | teacher |
| GET | `/api/teacher/students` | teacher |
| POST | `/api/teacher/students` | teacher |
| DELETE | `/api/teacher/students/{student_id}` | teacher |
| PUT | `/api/teacher/students/{student_id}` | teacher |
| GET | `/api/teacher/students/{student_id}/avatar` | teacher |
| POST | `/api/teacher/students/{student_id}/reset-face` | teacher |
| DELETE | `/api/teacher/subjects/{subject_id}` | teacher |
| PUT | `/api/teacher/subjects/{subject_id}` | teacher |
| GET | `/api/student/attendance` | student |
| GET | `/api/student/attendance/export.csv` | student |
| POST | `/api/student/attendance/scan` | student |
| DELETE | `/api/student/avatar` | student |
| GET | `/api/student/avatar` | student |
| POST | `/api/student/avatar` | student |
| GET | `/api/student/classes` | student |
| GET | `/api/student/face` | student |
| POST | `/api/student/face/enroll` | student |
| POST | `/api/student/password` | student |
| GET | `/api/student/profile` | student |
| PUT | `/api/student/profile` | student |
| GET | `/api/student/requests` | student |
| GET | `/api/student/sessions/active` | student |
| GET | `/api/student/sessions/{session_id}` | student |
| POST | `/api/student/sessions/{session_id}/join` | student |
| POST | `/api/student/sessions/{session_id}/join-face` | student |
| POST | `/api/student/sessions/{session_id}/request` | student |
