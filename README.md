# QuickMark
 Smart QR-based attendance system with rotating QR codes, face check and live reports. Flask + SQLite + C++ core.
QuickMark - Smart QR-Based Attendance Management System

QuickMark is a web-based attendance system for colleges. A teacher starts a session, the server shows a QR code that changes every 3 seconds, and students scan it from their own phones to mark attendance. A face check at joining time makes sure the right student is marking attendance.

Built as a college project-based learning (PBL) project using Flask, SQLite, Socket.IO and a C++17 core for the data-structure and OOP logic.

Features

Teacher site

Login, dashboard, classes / sections / subjects, student management
Attendance sessions with a live waiting room and a rotating server-made QR code
Group attendance (one session across sections of different classes)
Attendance history with filters, manual editing and CSV / Excel export
Reports with charts (overall, class-wise, section-wise, daily trend, low-attendance list)
Low-attendance warning emails and dashboard alerts
Bulk student import (CSV / paste), join codes for classes, password reset

Student site

Home with overall %, subject-wise attendance and "classes needed to reach required %"
Camera-based QR scanner
Face set-up on first login and face check before joining a session
Attendance history, profile, and correction requests after a session

Security

The server validates everything: login, session state, QR token, expiry, class membership and duplicates
A QR token is valid for only 5 seconds, so photos of old codes stop working
Only 128 face numbers are sent from the browser; live video is never uploaded
Rate limiting, wrong-face lockout, HTTPS (self-signed certificate)
Tech Stack
Part	Technology
Backend	Python, Flask, Flask-SocketIO
Database	SQLite
Core logic	C++17 (called from Python with ctypes)
Frontend	HTML, CSS, JavaScript
QR	qrcode (server), html5-qrcode (scanner)
Face check	face-api.js (models bundled, works offline)
Charts / Excel	Chart.js, openpyxl
C++ core (OOP + DSA)
File	What it does	Concepts
rate_limiter.hpp	Sliding-window rate limiter	hash map + deque, mutex
face.hpp	Face descriptor distance, wrong-face lockout	operator overloading, vector maths
stats.hpp	Percentages, advice, natural / stable sorting	merge sort, natural key compare
csv_writer.hpp	Safe CSV writing	RAII, single-pass escaping
How an Attendance Session Works
Teacher chooses class + section and starts a session (waiting room opens).
Students open the session, pass the face check and join.
Teacher presses START ATTENDANCE. Only now does the server create QR tokens.
A new token is made every 3 seconds and accepted for 5 seconds.
Students scan the QR with the in-app scanner.
Teacher presses End Attendance. Everyone who did not scan is saved as absent.
Getting Started

Requirements: Python 3.10+ (64-bit). No C++ compiler needed on Windows 64-bit or Linux 64-bit (prebuilt library included).

bash
# Windows
start.bat

# Mac / Linux
./start.sh

The start script checks Python, installs packages, loads the C++ core, asks you to create a teacher account on first run, creates the HTTPS certificate and starts the server.

Teacher site: https://localhost:5000/teacher/login.html
Student site: https://<server-laptop-IP>:5000/student/login.html

The browser shows a certificate warning the first time (self-signed). Click Advanced -> Proceed.

Manual setup

bash
pip install -r requirements.txt
cd backend
python create_teacher.py "Your Name" you@college.edu
python make_cert.py
python app.py

Using it on other devices: everyone must be on the same Wi-Fi as the server laptop. Run python make_cert.py after connecting to that network so the IP is inside the certificate, and allow Python through the firewall on port 5000.

Optional - real emails: set QUICKMARK_SMTP_HOST, QUICKMARK_SMTP_PORT, QUICKMARK_SMTP_USER, QUICKMARK_SMTP_PASSWORD and QUICKMARK_SMTP_TLS before starting the server (Gmail needs an app password). Without these, everything else still works.

Project Structure
quickmark/
├── backend/
│   ├── routes/        # API endpoints
│   ├── services/      # business logic
│   ├── middleware/
│   ├── database/      # schema + SQLite file
│   └── cpp/           # C++ core (OOP + DSA) and prebuilt libraries
├── frontend/
│   ├── teacher/       # teacher pages
│   ├── student/       # student pages
│   ├── css/  js/
│   └── vendor/        # bundled libraries and face models
├── docs/ARCHITECTURE.md   # architecture, database and API reference
├── tests/
├── start.py  start.bat  start.sh
└── requirements.txt
Tests

Tests use temporary databases, so real data is never touched.

bash
python tests/test_stage1.py        # ... up to test_stage11.py
python tests/test_cpp_core.py      # compares C++ with the original Python logic
python backend/build_cpp.py --test # native C++ tests
Limitations
The face check has no liveness detection, so a photo of a student might fool it. Treat it as a deterrent.
A teacher and a student cannot be logged in on the same browser at the same time (use two browsers or incognito).
For use outside the local network you need a tunnel such as ngrok, or a hosted server.


Documentation

Full architecture, database tables, security notes and API list: docs/ARCHITECTURE.md
