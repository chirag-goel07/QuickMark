PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    must_change_password INTEGER NOT NULL DEFAULT 0    -- 1 = the teacher set this password; the student must choose their own at first login
);

CREATE TABLE IF NOT EXISTS teachers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    phone             TEXT,
    warning_threshold INTEGER NOT NULL DEFAULT 75 CHECK (warning_threshold BETWEEN 1 AND 100),
    session_minutes   INTEGER NOT NULL DEFAULT 10 CHECK (session_minutes BETWEEN 1 AND 180),
    require_face      INTEGER NOT NULL DEFAULT 0 CHECK (require_face IN (0, 1)),  -- 1 = students must scan their face to join
    auto_alerts       INTEGER NOT NULL DEFAULT 0,      -- 1 = also EMAIL students when their attendance drops below the threshold (in-app notice is always sent)
    weekly_summary    INTEGER NOT NULL DEFAULT 0,      -- 1 = email the teacher a weekly low-attendance summary
    last_summary_at   TEXT
);

CREATE TABLE IF NOT EXISTS classes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    UNIQUE (teacher_id, name)
);

CREATE TABLE IF NOT EXISTS sections (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    join_code TEXT,                                   -- students can join this section with the code (see join_mode)
    join_mode TEXT NOT NULL DEFAULT 'off',            -- off | open (joins at once) | approval (teacher approves each one)
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS subjects (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    UNIQUE (class_id, name)
);

-- One row per ENROLLMENT: a person (one login = one users row) has one students row for every class/section they are in.
-- So the same roll number can exist in different sections, and the same email can be in DSA and OOPS.
CREATE TABLE IF NOT EXISTS students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    roll_no    TEXT NOT NULL,
    name       TEXT NOT NULL,
    phone      TEXT,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    face_descriptor  TEXT,                            -- 128 numbers (a face "template"), never a photo; never sent to any browser
    face_enrolled_at TEXT,
    avatar           BLOB,                            -- small profile picture (JPEG, max 200 KB) chosen by the student
    avatar_updated_at TEXT,
    UNIQUE (section_id, roll_no),                     -- roll numbers only have to be unique inside one section
    UNIQUE (section_id, user_id)                      -- a person is in a section only once
);
CREATE INDEX IF NOT EXISTS idx_students_user ON students(user_id);

CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    UNIQUE (teacher_id, name)
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, student_id)
);

-- A group is made of whole SECTIONS (the teacher ticks sections); its students are always the students currently in those sections.
-- (Older groups that were made by picking single students have no rows here and keep their own member list.)
CREATE TABLE IF NOT EXISTS group_sections (
    group_id   INTEGER NOT NULL REFERENCES groups(id)   ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, section_id)
);

-- One row per attendance session. Normal = section_id set, Group = group_id set.
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id       INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    session_type     TEXT NOT NULL CHECK (session_type IN ('normal', 'group')),
    section_id       INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    group_id         INTEGER REFERENCES groups(id)   ON DELETE SET NULL,
    subject_id       INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    label            TEXT NOT NULL,                  -- readable name kept for history
    status           TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'ended')),
    duration_minutes INTEGER NOT NULL,
    total_students   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at       TEXT,
    ended_at         TEXT
);

-- Students who joined the waiting room. A student can join a session only once.
CREATE TABLE IF NOT EXISTS session_participants (
    session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    joined_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, student_id)
);

-- Short-lived rotating QR tokens, generated and validated by the server.
CREATE TABLE IF NOT EXISTS qr_tokens (
    token      TEXT PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL                          -- unix timestamp (seconds)
);
CREATE INDEX IF NOT EXISTS idx_qr_session ON qr_tokens(session_id);

-- Duplicate attendance is blocked by the PRIMARY KEY (session_id, student_id).
CREATE TABLE IF NOT EXISTS attendance_records (
    session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status     TEXT NOT NULL CHECK (status IN ('present', 'absent')),
    marked_at  TEXT NOT NULL DEFAULT (datetime('now')),
    marked_via TEXT NOT NULL DEFAULT 'qr',            -- qr | teacher (manual edit) | request (teacher approved a request)
    PRIMARY KEY (session_id, student_id)
);

CREATE TABLE IF NOT EXISTS email_notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('mailto_opened', 'sent')),
    subject    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A student who could not join/scan asks the teacher to mark them present.
CREATE TABLE IF NOT EXISTS attendance_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    message     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    created_at  TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE (session_id, student_id)                   -- one request per student per session
);

-- Every manual change to attendance is logged (who/what/when) so edits can be audited.
CREATE TABLE IF NOT EXISTS attendance_edits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    old_status TEXT,                                  -- NULL = there was no record
    new_status TEXT,                                  -- NULL = record removed (un-marked while the session was running)
    kind       TEXT NOT NULL CHECK (kind IN ('edit', 'request')),
    created_at TEXT NOT NULL
);


-- ---- forgot password: a 6-digit code, only its keyed hash is stored; valid 15 minutes; max 5 wrong tries
CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT NOT NULL,
    expires_at REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0
);

-- ---- students asking to join a section with its code (only used when join_mode = 'approval')
CREATE TABLE IF NOT EXISTS join_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id    INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,   -- set when an existing student asks; NULL for a brand-new signup
    name          TEXT NOT NULL,
    roll_no       TEXT NOT NULL,
    email         TEXT NOT NULL,
    phone         TEXT,
    password_hash TEXT,                                              -- only for new signups (becomes their login when approved)
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---- small in-app messages for students (low attendance, join request answered)
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_read    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, id);

-- ---- one low-attendance alert per enrollment per week (no spam)
CREATE TABLE IF NOT EXISTS alert_log (
    student_id    INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    last_alert_at REAL NOT NULL
);
