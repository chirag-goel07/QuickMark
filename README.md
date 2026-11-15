# QuickMark - Smart QR-Based Attendance (Flask)

QuickMark has: login, dashboard, classes/sections/subjects, students, **attendance sessions with a live
waiting room, server-made rotating QR codes, a student website (home, classes, attendance, profile with picture)
with a camera scanner, group attendance, attendance history, reports with charts, settings, low-attendance warning emails,
a face check (set up once at first login), student requests after a session, and teacher attendance editing**.
More detail for your report: `docs/ARCHITECTURE.md` (architecture, database tables, security, full API list).

## 1. Install and run (on the server laptop)
**Easy way (recommended):**
1. Install **Python 3.10 or newer, 64-bit** from https://www.python.org/downloads/ (on Windows tick **"Add python.exe to PATH"**).
2. **Windows:** double-click **`start.bat`**.   **Mac / Linux:** run `./start.sh`.

That one file does everything and prints what it is doing in 6 numbered steps: checks Python, installs the packages (needs internet the first
time), loads the C++ core (a ready-made library for Windows 64-bit and Linux 64-bit is included, **no compiler needed**), asks you for a teacher
name / email / password the first time, makes the HTTPS certificate, and starts the server. At the end it prints the teacher and student addresses.
If something is wrong it stops with a sentence saying what and how to fix it. `python start.py --check` only looks at the computer and prints a report
without changing anything (send that output to whoever helps you).

Teacher site: `https://localhost:5000/teacher/login.html`.  Student site: `https://<server-laptop-IP>:5000/student/login.html`.
Keep the window open while using QuickMark; **Ctrl+C** stops it.

**Manual way (only if you prefer):** `pip install -r requirements.txt`, then in `backend`: `python create_teacher.py "Your Name" you@college.edu`,
`python make_cert.py`, `python app.py`. A C++ compiler is needed only on a computer the ready-made library does not fit (Mac, 32-bit Python,
old Linux); then run `cd backend` and `python build_cpp.py`.

The first time a browser opens the site it shows a warning (the certificate is self-signed).
Click **Advanced -> Proceed**. Students must do this once on their device.

## 2. Connecting other laptops / phones
- Everyone must be on the **same Wi-Fi/network** as the server laptop.
- Find the server laptop's IP: Windows `ipconfig` (IPv4 address), Mac/Linux `ifconfig` or `ip a`.
- Run `python make_cert.py` AFTER you connect to that network, so the IP is inside the certificate.
- If others cannot connect, allow Python through the server laptop's firewall (port 5000).
- For use over the internet (not same network) you need a tunnel such as ngrok, or a hosted server.

## 3. How an attendance session works
1. Teacher: **Take Attendance** -> choose class + section -> Start Attendance -> *waiting room*.
2. Students: open the session and press **Check face & join session** (or **Join session** if face check is off). The teacher sees the joined count and percentage update live.
3. Teacher presses **START ATTENDANCE** -> only now does the server create a QR token and show the QR.
4. The server makes a new token every 3 seconds. A token is accepted for 5 seconds (3s showing + 2s for scanning
   and network), so an old or photographed code stops working almost immediately.
5. Students press **Open scanner**, allow the camera, and scan. The server checks login, session state,
   token, expiry, class/group membership and duplicates.
6. Teacher presses **End Attendance** (or the session duration runs out): everyone who did not scan is saved
   as absent and the session is final.

Tip: the teacher and a student can't be logged in at the same time in the *same browser*
(they share one login cookie). Use two browsers, or a private/incognito window, when testing on one laptop.

## 4. Group attendance
Teacher: **Group Attendance** (dashboard button) -> *Create Group* -> name it -> choose a **class** -> tick the **sections** that take this attendance (you can switch class and tick sections of other classes too). No students are listed there: the group is everyone in the ticked sections, and students added to those sections later are included automatically. -> *Start Attendance*. From there it is exactly the same
waiting room -> START ATTENDANCE -> QR -> End flow as section attendance. Only group members can see, join or
scan a group session. A group can't be edited or deleted while its session is open.

## 5. History, reports and settings (teacher)
- **Attendance History**: every finished session (date, class/group, subject, total, present, absent, %). Filter by
  class, type and dates; click *View* for the present/absent names; *Export CSV* downloads the list (or one session).
- **Reports**: overall %, class-wise and section-wise charts, a daily trend, the low-attendance list and a sortable
  student-wise table. Every table has a CSV button. Charts need no internet (bundled in `frontend/vendor`).
- **Settings**: your name/phone, the **warning threshold** (default 75%), the **default session duration**, and password change.

## 6. Low-attendance warning emails
Students below the threshold appear on the dashboard (and Reports / Students pages).
- **Email Warning** (one student): opens *your own email app* with the address, subject and message already filled in
  (student's name, their percentage, the required threshold, your name). **Nothing is sent until you press Send there.**
- **Email All**: gives two clearly separate options:
  1. *Open a draft* - one general message with every address in BCC (students can't see each other). Not sent until you send it.
  2. *Send from the server* - QuickMark sends one **personal** email per student. This only works after you set up an
     email account on the server (below). Email passwords live only in the server's environment, never in the web pages.
- Sending real emails (optional). Set these before `python app.py`. Gmail needs an *app password*, not your normal one:
  - Windows (cmd): `set QUICKMARK_SMTP_HOST=smtp.gmail.com` `set QUICKMARK_SMTP_PORT=587` `set QUICKMARK_SMTP_USER=you@gmail.com`
    `set QUICKMARK_SMTP_PASSWORD=your-app-password` `set QUICKMARK_SMTP_TLS=starttls`
  - Mac/Linux: the same with `export NAME=value`.
- Opening a draft and sending are recorded separately in the database (`mailto_opened` vs `sent`).

## 7. Student website
After the first login a student sees: **Home** (overall %, how many classes to attend to reach the required %, present/absent/this-month
numbers, open sessions, subject-wise attendance, recent attendance, status of their requests), **Classes** (their class, section, teacher,
every subject with their own attendance, and their groups), **Attendance** (full history, requests, CSV download) and **Profile**
(profile picture, phone number, face status, change password, download my data). A student only ever sees their own records.

## 8. Face check, profile picture, requests and editing attendance
**Face check (on by default for teachers made with `create_teacher.py`; switch it in Settings).**
- **First login:** the student is taken straight to *Set up your face* (3 quick captures, after reading a privacy note). The small photo taken during this scan
  automatically becomes the student's profile picture. This is done once, *before* any session, not in the middle of one. "Not now" skips it for that browser session
  (a student with a broken camera can still reach everything except joining).
- **Every session:** the student presses *Check face & join session*; only if the face matches do they enter the waiting room.
- Privacy: for every attendance scan the browser turns the camera picture into **128 numbers** and sends only those. The live video is never uploaded.
  The only picture ever sent is **one small cropped photo at the first set-up**, stored as the profile picture.
  The Students page shows who is set up and has **Reset face** (the student then sets it up again, which also makes a new picture).
- A wrong face is refused; 5 wrong tries in a minute lock the student out briefly. Face models are bundled (works offline).
- Honest limits: there is **no liveness check** (a photo of the student might fool it) and the first set-up is not
  supervised unless you are present. Treat it as a deterrent and keep watching the room.

**Profile picture.** It is the small photo (256x256 JPEG, stored in the database, max 200 KB) taken during the student's **first face set-up**. Students
**cannot upload, change or remove it**, so nobody can swap in a fake face afterwards; only the teacher's **Reset face** removes it (the next set-up
takes a new one). Teachers see it next to the student's requests, in the Students list and in History. Only the student's own teacher can see it.
Honest limit: the server cannot check that the photo really matches the 128 numbers (that needs the browser), so a technical student could craft the
first request by hand; the teacher can see the picture and reset it.

**Requests (my attendance was not marked).** Requests are sent **after the session has ended**: in *Attendance* a student marked absent sees
**Request correction**. The dialog shows their name and small picture, and the same picture appears with the request on the teacher's side.
- Works for `7` days after the session (`QUICKMARK_REQUEST_DAYS`). One request per student per session; a rejected request cannot be repeated.
- Teachers see requests on the **dashboard**, as a ✉ badge in **Attendance History**, and inside the session's detail. **Accept** makes the student
  present and updates all percentages; **Reject** leaves it as it was.
- To also allow requests while a session is still running, start the server with `QUICKMARK_REQUESTS_DURING_SESSION=1`.

**Editing attendance (teacher).**
- While a session runs: *Mark a student present manually* (for students who cannot scan).
- After it ended: **Attendance History -> View**: press *Mark present / Mark absent* next to any student.
- Percentages, reports and student pages update immediately. Every manual change and approved request is saved in an
  audit table (`attendance_edits`), and the CSV export has a *Marked by* column (QR scan / Teacher edit / Request approved).

## 9. Testing on two real devices (checklist for your demo)
1. Server laptop: `python make_cert.py` (while on the college Wi-Fi), then `python app.py`.
2. Teacher opens `https://localhost:5000/teacher/login.html`. Student phone/laptop opens `https://<server-IP>:5000/student/login.html`
   and accepts the certificate warning once.
3. Teacher: add a class, a section and a few students (Students page). Give each student their password.
4. Student logs in for the first time -> *Set up your face* (the photo of that scan becomes the profile picture). Later: opens the session -> *Check face & join* -> appears in the teacher's waiting room.
5. Teacher: *START ATTENDANCE* -> QR appears and changes every 3 seconds. Student: *Open scanner* -> scan -> "Attendance marked".
6. Teacher: *End Attendance* -> check *Attendance History*, *Reports* and the dashboard's low-attendance list.
7. Try the extras: after the session a student uses *Request correction*, the teacher sees the request with the student's picture and accepts it;
   edit a student in History; restart the server and confirm everything is still there.

## 10. Tests (temporary databases only - your real data is never touched)
From this folder:
`python tests/test_stage1.py`, `test_stage2.py`, `test_stage3.py`, `test_stage3b.py`, `test_stage4.py`, `test_stage5.py`, `test_stage6.py`, `test_stage7.py`, `test_stage8.py`, `test_stage9.py` (all in `tests/`).
C++ core: `python tests/test_cpp_core.py` (compares C++ with the original Python logic on thousands of random inputs) and `python backend/build_cpp.py --test` (native C++ tests).
The email tests use a tiny fake mail server (`tests/smtp_sink.py`), so no real email is sent.

## 11. Folders
- `backend/` Flask server: `routes/` (API), `services/` (logic), `middleware/`, `database/` (schema + SQLite file)
- `backend/cpp/` **C++ core: the OOP and DSA logic** (see section 12). `backend/build_cpp.py` builds it, `backend/services/core.py` connects it to Flask
- `frontend/teacher`, `frontend/student` (pages), `frontend/css`, `frontend/js`, `frontend/vendor` (socket.io, QR scanner, charts and face models, all bundled so no internet is needed)
- `docs/ARCHITECTURE.md` architecture, database and API reference


## 9. Students in several classes, bulk import, passwords, editing (latest changes)
- **Roll numbers** only have to be unique *inside one section* (ML1 roll 1 and ML2 roll 1 are fine).
- **One student, many classes:** adding an email that already has a QuickMark login just adds that person to the new class/section.
  Their password, face and picture stay the same, and the student sees every class on one login. Removing a student from one class
  keeps their other classes. Existing databases are upgraded automatically the first time the server starts (data is kept).
- **Students page:** the list is shown section by section (pick a class and a section in the filters to see only that section). **Click a student's name** to see their details: class/section, overall and subject-wise attendance, and recent sessions.
- **Adding many students:** Students page -> *Import many (CSV / paste)*. Pick the section, upload a CSV (or paste rows from Excel),
  optionally set one common first password (otherwise each student gets a random one). Bad rows are skipped with a reason; good rows are saved.
  Afterwards you can download the list of first passwords (shown only once).
- **Passwords:** the teacher sets (or the system generates) a *first* password. The student logs in normally and can change it any time in Profile -> Change password.
- **Editing attendance:** not possible while a session is running. After End Attendance, open *Edit attendance*; there is one box per section (e.g. DSA - ML1, DSA - ML2).

## 10. Forgot password, join codes, alerts, Excel (latest changes)
**Install the new dependency once:** `pip install -r requirements.txt` (adds `openpyxl` for Excel files).

**Email (needed for "Forgot password" mails, emailing students and the weekly summary).** Set these before starting the server:
`QUICKMARK_SMTP_HOST`, `QUICKMARK_SMTP_PORT`, `QUICKMARK_SMTP_USER`, `QUICKMARK_SMTP_PASSWORD`, `QUICKMARK_SMTP_TLS` (see `config.py`; Gmail needs an app password).
Without email everything else still works: the Forgot-password page tells students to ask their teacher, and the teacher uses **Reset password** on the Students page.

- **Forgot password** (login pages -> "Forgot password?"): a 6-digit code is emailed, valid 15 minutes, 5 wrong tries then locked, works once, max 3 mails per hour per email.
  The answer is the same for unknown emails, so nobody can find out who is registered. Teachers can use it too.
- **Reset password (teacher):** Students page -> *Reset password* gives the student a new random password (shown once).
- **Join with a class code:** Classes page -> the 🔗 next to a section. Choose *Open* (students join at once) or *Needs my approval*, then share the code or link.
  Students open `/student/join.html` (also linked from the student login page), type the code and create their own login, or - when already logged in - join one more class from their dashboard.
  Approvals are on the Students page -> *Join requests*. *New code* stops the old code immediately. Open mode does not verify emails, so share the code only with your class (or use approval).
- **Low-attendance alerts:** when a session ends, students below the threshold get a dashboard notification (once a week at most). Settings -> *Low-attendance alerts* adds emails to students and a weekly summary email for you.
- **Excel:** Reports -> *Excel (sheet per section)* (summary, below-threshold list and one sheet per section with a % column per subject); History -> a session -> *Excel* (one sheet per section).


## 12. C++ core (OOP + DSA)
Flask (backend) and HTML/CSS/JS (frontend) are unchanged. The parts that are really OOP or data-structure/algorithm logic are written in **C++17** in `backend/cpp/`,
compiled to a shared library, and called from Python with `ctypes` (`backend/services/core.py`, no extra pip package).

| C++ file | Class(es) | OOP used | DSA used | Replaced Python |
|---|---|---|---|---|
| `rate_limiter.hpp` | `SlidingWindowLimiter` | encapsulation, thread safety (mutex) | hash map of key -> deque of times (sliding window) | `services/ratelimit.py` |
| `face.hpp` | `FaceDescriptor`, `LockoutTracker`, `captures_consistent` | value class, operator overloading (`a - b` = distance), static factories | vector maths, pairwise check O(k^2), hash map of id -> deque | maths + lock-out in `services/face.py` |
| `stats.hpp` | `AttendanceStats`, `NaturalKey`, `Advice` | value classes with behaviour, `operator<` | stable merge sort on an index array, tokenising scan, ceiling division | percentages, advice, low-list sort, roll-number sort, streak |
| `csv_writer.hpp` | `CsvWriter` | RAII (owned through a handle), encapsulated buffer | single-pass quoting / escaping | `services/csvutil.py` (CSV + Excel safety) |
| `quickmark_core.cpp` | C interface (`qm_*`) | - | - | the only file Python talks to |

Things worth saying in your viva/report: the sliding window removes expired timestamps then compares the size to the limit; natural order splits `A10` into
text/number chunks so `A9 < A10` (numbers compare as big integers, so `007 = 7`); percentages are rounded exactly like Python's `round(x, 1)`.
Everything else (database queries, routes, sessions, QR tokens, e-mail, Socket.IO) is still Python.
