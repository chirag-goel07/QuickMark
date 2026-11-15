"""Profile pictures. A student cannot upload or change their picture: it is the small photo taken by the camera during the
FIRST face setup (the browser crops it to the face and shrinks it to a small JPEG; the server still checks everything itself).
Only a teacher's "Reset face" removes it, and the student's next face setup takes a new one."""
import base64
import binascii

from flask import Response

MAX_BYTES = 200 * 1024


def validate_jpeg(data, mimetype):
    """Returns an error message, or None if the upload is acceptable."""
    if mimetype != "image/jpeg":
        return "Please send a JPEG picture."
    if not data:
        return "No picture received."
    if len(data) > MAX_BYTES:
        return "That picture is too big (maximum 200 KB). It is shrunk automatically in the app."
    if not (data[:3] == b"\xff\xd8\xff" and data[-2:] == b"\xff\xd9"):
        return "That file is not a valid JPEG picture."
    return None


def decode_photo(b64):
    """The face-setup photo arrives as base64 text. Returns (jpeg_bytes, None) or (None, error message)."""
    if not isinstance(b64, str) or not b64:
        return None, "The photo from your face scan is missing. Reload the page and try again."
    if len(b64) > MAX_BYTES * 4 // 3 + 16:
        return None, "That picture is too big (maximum 200 KB)."
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None, "The photo from your face scan could not be read. Try again."
    err = validate_jpeg(data, "image/jpeg")
    return (None, err) if err else (data, None)


def avatar_response(db, student_id):
    row = db.execute("SELECT avatar FROM students WHERE id = ?", (student_id,)).fetchone()
    if not row or row["avatar"] is None:
        return Response("No picture.", status=404, mimetype="text/plain")
    return Response(bytes(row["avatar"]), mimetype="image/jpeg", headers={
        "X-Content-Type-Options": "nosniff",                    # never treated as anything but an image
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, max-age=300"})
