"""QuickMark launcher - one command does the whole setup and starts the server, and says what it is doing.

    python start.py            set everything up (first time only) and start the server
    python start.py --check    only look at this computer and print a report (nothing is changed)

Windows: double-click start.bat      Mac/Linux: ./start.sh
"""
import importlib.util
import os
import socket
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
CHECK_ONLY = "--check" in sys.argv
PORT = 5000
PACKAGES = {"flask": "Flask", "flask_socketio": "Flask-SocketIO", "simple_websocket": "simple-websocket",
            "qrcode": "qrcode", "cryptography": "cryptography", "openpyxl": "openpyxl"}


def say(text=""):
    print(text, flush=True)


def step(n, title):
    say(f"\n[{n}/6] {title}")


def ok(text):
    say(f"      OK   {text}")


def warn(text):
    say(f"      !!   {text}")


def stop(problem, *how_to_fix):
    say(f"\n      PROBLEM: {problem}")
    for line in how_to_fix:
        say(f"      -> {line}")
    say("\nQuickMark did not start. Fix the problem above and run this again.")
    sys.exit(1)


def missing_packages():
    return [pip for mod, pip in PACKAGES.items() if importlib.util.find_spec(mod) is None]


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    say("=" * 60)
    say("  QuickMark " + ("- setup check (nothing is changed)" if CHECK_ONLY else "- starting"))
    say("=" * 60)

    # 1 ------------------------------------------------------------------ Python
    step(1, "Python")
    v = sys.version_info
    if v < (3, 10):
        stop(f"This is Python {v.major}.{v.minor}; QuickMark needs 3.10 or newer.",
             "Install the newest Python from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run again.")
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    ok(f"Python {v.major}.{v.minor}.{v.micro} ({bits}-bit)  {sys.executable}")
    if bits == 32:
        warn("32-bit Python: the ready-made C++ library is 64-bit, so a C++ compiler would be needed. A 64-bit Python is much easier.")

    # 2 ------------------------------------------------------------------ packages
    step(2, "Python packages (Flask and friends)")
    missing = missing_packages()
    if not missing:
        ok("all installed")
    elif CHECK_ONLY:
        warn("missing: " + ", ".join(missing) + "   (start.py installs them for you)")
    else:
        say("      Installing: " + ", ".join(missing) + "  (first time only, about a minute, needs internet)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")],
                           capture_output=True, text=True)
        if r.returncode != 0 or missing_packages():
            tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])
            stop("Installing the packages failed.", "Last lines of the installer:", *["    " + l for l in tail.splitlines()],
                 "Check your internet connection, then run again. (Manual way:  python -m pip install -r requirements.txt)")
        ok("installed")

    # 3 ------------------------------------------------------------------ C++ core
    step(3, "C++ core (the OOP / DSA part)")
    if missing_packages():
        warn("skipped until the packages are installed")
    else:
        sys.path.insert(0, BACKEND)
        try:
            from services import core
            where = os.path.relpath(core.LIBRARY_PATH, ROOT)
            ok(f"{core.version()}  <-  {where}")
        except Exception as e:                                       # noqa: BLE001
            stop("The C++ core could not be loaded.", *str(e).splitlines())

    # 4 ------------------------------------------------------------------ teacher account
    step(4, "Teacher account")
    if missing_packages():
        warn("skipped until the packages are installed")
    else:
        import config
        from database.db import _connect, init_db
        if CHECK_ONLY and not os.path.exists(config.DATABASE_PATH):
            warn("no database yet (start.py creates it and asks for a teacher name, email and password)")
        else:
            init_db(config.DATABASE_PATH)
            conn = _connect(config.DATABASE_PATH)
            teachers = [r[0] for r in conn.execute("SELECT u.email FROM teachers t JOIN users u ON u.id = t.user_id").fetchall()]
            conn.close()
            if teachers:
                ok("login email: " + ", ".join(teachers))
            elif CHECK_ONLY:
                warn("no teacher account yet (start.py asks you for one)")
            else:
                say("      No teacher account yet - let's make one (this is what you log in with).")
                while True:
                    name = input("      Your name (e.g. Ms. Sharma): ").strip()
                    email = input("      Your email (used to log in):  ").strip()
                    if name and "@" in email:
                        break
                    say("      Please type a name and a real-looking email.")
                r = subprocess.run([sys.executable, os.path.join(BACKEND, "create_teacher.py"), name, email], cwd=BACKEND,
                                   env={**os.environ, "QUICKMARK_LAUNCHER": "1"})
                if r.returncode != 0:
                    stop("The teacher account was not created (see the message above).", "Run start again and re-type the details.")
                ok("teacher account created")

    # 5 ------------------------------------------------------------------ HTTPS
    step(5, "HTTPS certificate (needed for the phone camera)")
    certs = os.path.join(BACKEND, "certs")
    have_cert = os.path.exists(os.path.join(certs, "cert.pem")) and os.path.exists(os.path.join(certs, "key.pem"))
    if have_cert:
        ok("found")
    elif CHECK_ONLY or missing_packages():
        warn("not made yet (start.py makes it)")
    else:
        r = subprocess.run([sys.executable, os.path.join(BACKEND, "make_cert.py")], cwd=BACKEND, capture_output=True, text=True)
        have_cert = r.returncode == 0
        ok("created") if have_cert else warn("could not create it; the site will run on http (fine on this laptop, phones cannot use the camera).\n" + r.stderr[-300:])

    # 6 ------------------------------------------------------------------ port
    step(6, f"Port {PORT}")
    if port_free(PORT):
        ok("free")
    else:
        msg = f"Port {PORT} is already used - most likely QuickMark is already running in another window."
        if CHECK_ONLY:
            warn(msg)
        else:
            stop(msg, "Close the other QuickMark window (or the program using the port), then run this again.")

    if CHECK_ONLY:
        say("\nCheck finished. If everything above says OK, run:  python start.py")
        return

    scheme = "https" if have_cert else "http"
    ip = lan_ip()
    say("\n" + "=" * 60)
    say("  QuickMark is starting. Keep this window OPEN while using it.")
    say(f"  Teacher (this laptop):  {scheme}://localhost:{PORT}/teacher/login.html")
    if ip:
        say(f"  Students (same Wi-Fi):  {scheme}://{ip}:{PORT}/student/login.html")
    if have_cert:
        say("  The browser warns about the certificate the first time: click Advanced -> Proceed.")
    say("  Stop the server with Ctrl+C.")
    say("=" * 60 + "\n")
    try:
        code = subprocess.call([sys.executable, "app.py"], cwd=BACKEND)
    except KeyboardInterrupt:
        say("\nQuickMark stopped.")
        return
    if code != 0:
        say(f"\nThe server stopped with an error (code {code}). Read the red/last lines above - they say what went wrong.")
        say("If you cannot fix it, run  python start.py --check  and send that output to whoever helps you.")
        sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nStopped.")
