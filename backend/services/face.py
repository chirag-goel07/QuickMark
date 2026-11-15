"""Face verification on the SERVER.
The browser turns a camera picture into 128 numbers (a "descriptor"). Scans for attendance send only those numbers; the first-time setup
also sends ONE small cropped photo that becomes the profile picture.
No photo is ever uploaded or stored. The server compares the numbers with the student's enrolled ones.
"""
import json

import config
from services import core, people
from services.sessions import SessionError, ts_to_str

DIM = 128
SAMPLE_CONSISTENCY = 0.45        # enrollment photos must look like the same person

# The maths (distance, average, consistency check) and the wrong-face lock-out table are the C++ classes
# qm::FaceDescriptor and qm::LockoutTracker (cpp/face.hpp). The lock-out is memory only: it resets when the server restarts.


def parse_descriptor(raw):
    if not isinstance(raw, list) or len(raw) != DIM:
        raise SessionError("Invalid face data.", 400)
    try:
        vec = [float(x) for x in raw]
    except (TypeError, ValueError):
        raise SessionError("Invalid face data.", 400)
    if not core.face_is_valid(vec):
        raise SessionError("Invalid face data.", 400)
    return vec


def distance(a, b):
    return core.face_distance(a, b)


def enrolled_descriptor(db, student_id):
    row = db.execute("SELECT face_descriptor FROM students WHERE id = ?", (student_id,)).fetchone()
    return json.loads(row["face_descriptor"]) if row and row["face_descriptor"] else None


def enroll(db, student_id, samples, now, photo=None):
    """`photo` = the small JPEG the browser took during this first scan; it becomes the profile picture (the student cannot change it)."""
    if enrolled_descriptor(db, student_id) is not None:
        raise SessionError("Your face is already enrolled. Ask your teacher to reset it if it needs to change.", 409)
    if not isinstance(samples, list) or not 3 <= len(samples) <= 6:
        raise SessionError("Capture your face 3 times to enroll.", 400)
    vecs = [parse_descriptor(s) for s in samples]
    same_face, avg = core.face_enroll(vecs, SAMPLE_CONSISTENCY)
    if not same_face:
        raise SessionError("The captures did not look like the same face. Hold still, face the camera and try again.", 400)
    columns = dict(face_descriptor=json.dumps(avg), face_enrolled_at=ts_to_str(now))
    if photo is not None:
        columns.update(avatar=photo, avatar_updated_at=ts_to_str(now))
    people.set_person_columns(db, student_id, **columns)         # same face (and picture) for every class of this person
    db.commit()


def reset(db, student_id):
    """Teacher's "Reset face": forgets the face AND the picture taken from it; the next face setup makes both again."""
    people.set_person_columns(db, student_id, face_descriptor=None, face_enrolled_at=None, avatar=None, avatar_updated_at=None)
    db.commit()
    core.lockout_clear(student_id)


def verify(db, student_id, raw_descriptor, now):
    """Raises SessionError (with a code the page understands) unless the face matches. Returns the distance."""
    if core.lockout_is_locked(student_id, now, config.FACE_FAIL_WINDOW, config.FACE_MAX_FAILS):
        raise SessionError("Too many failed face scans. Wait a minute, or send a request to your teacher.", 429, "face_locked")
    live = parse_descriptor(raw_descriptor)
    ref = enrolled_descriptor(db, student_id)
    if ref is None:
        raise SessionError("Enroll your face first.", 409, "not_enrolled")
    d = distance(live, ref)
    if d > config.FACE_MATCH_THRESHOLD:
        core.lockout_fail(student_id, now)
        raise SessionError("This face does not match the student account. Try again, or send a request to your teacher.", 403, "face_mismatch")
    core.lockout_clear(student_id)
    return d
