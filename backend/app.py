import os
import sys

# Lets "from database.db import ..." work when running `python app.py` from the backend folder.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, redirect, send_from_directory

import config
from database import db as database
from extensions import socketio
from routes import auth, classes, dashboard, emails, groups, history, join, reports, sessions, settings, student, students
from services import alerts, realtime


def create_app(database_path=None):
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_PATH"] = database_path or config.DATABASE_PATH
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024          # nothing in this app needs more than 1 MB per request
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    database.init_db(app.config["DATABASE_PATH"])
    app.teardown_appcontext(database.close_db)

    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(classes.bp)
    app.register_blueprint(students.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(emails.bp)
    app.register_blueprint(sessions.bp)
    app.register_blueprint(student.bp)
    app.register_blueprint(join.teacher_bp)
    app.register_blueprint(join.public_bp)
    app.register_blueprint(join.student_bp)

    socketio.init_app(app, async_mode="threading")
    realtime.register_socket_handlers()

    @app.errorhandler(413)
    def too_big(_e):
        from flask import jsonify
        return jsonify(error="That file is too large."), 413

    fe = config.FRONTEND_DIR

    @app.get("/")
    def home():
        return redirect("/teacher/login.html")

    @app.get("/teacher/<path:name>")
    def teacher_pages(name):
        return send_from_directory(os.path.join(fe, "teacher"), name)

    @app.get("/student/<path:name>")
    def student_pages(name):
        return send_from_directory(os.path.join(fe, "student"), name)

    @app.get("/vendor/<path:name>")
    def vendor(name):
        return send_from_directory(os.path.join(fe, "vendor"), name)

    @app.get("/css/<path:name>")
    def css(name):
        return send_from_directory(os.path.join(fe, "css"), name)

    @app.get("/js/<path:name>")
    def js(name):
        return send_from_directory(os.path.join(fe, "js"), name)

    return app


def run_server():
    app = create_app()
    socketio.start_background_task(realtime.rotation_loop, app.config["DATABASE_PATH"])   # rotates QR tokens
    socketio.start_background_task(alerts.maintenance_loop, app.config["DATABASE_PATH"], socketio.sleep)   # weekly teacher summary
    ssl_context = None
    cert, key = os.path.join(config.BASE_DIR, "certs", "cert.pem"), os.path.join(config.BASE_DIR, "certs", "key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        ssl_context = (cert, key)                      # HTTPS => phones/laptops are allowed to use the camera
    scheme = "https" if ssl_context else "http"
    app.config["SESSION_COOKIE_SECURE"] = bool(ssl_context)       # over HTTPS the login cookie is never sent in clear text
    print(f"\nQuickMark running.  Teacher: {scheme}://localhost:5000/teacher/login.html"
          f"   Student: {scheme}://<this-laptop-IP>:5000/student/login.html\n")
    # host 0.0.0.0 lets other laptops on the same network reach this server
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True, ssl_context=ssl_context)


if __name__ == "__main__":
    run_server()
