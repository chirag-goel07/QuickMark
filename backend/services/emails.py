"""Low-attendance warning emails.
  * mailto  = the browser opens the teacher's own email app with a draft (nothing is sent by us)
  * send    = the SERVER sends through SMTP (only if configured; credentials stay on the server)
"""
import smtplib
import ssl
from email.message import EmailMessage

import config


def _clean_line(text):
    return " ".join(str(text).split())            # no line breaks inside a header value


def fmt_pct(p):
    return f"{p:g}%"


def warning_message(teacher_name, student_name, percentage, threshold):
    subject = f"Attendance warning: {fmt_pct(percentage)} (minimum required {threshold}%)"
    body = (f"Dear {student_name},\n\n"
            f"This is a reminder that your current attendance is {fmt_pct(percentage)}, "
            f"which is below the required minimum of {threshold}%.\n\n"
            f"Please attend your upcoming classes regularly to improve your attendance. "
            f"If you have a valid reason for your absences, please contact me.\n\n"
            f"Regards,\n{teacher_name}")
    return subject, body


def bulk_message(teacher_name, threshold):
    """One generic draft for 'Email all' (recipients go in BCC, so no individual percentages)."""
    subject = f"Attendance warning: below the required {threshold}%"
    body = (f"Dear student,\n\n"
            f"Your attendance is currently below the required minimum of {threshold}%.\n\n"
            f"Please attend your upcoming classes regularly to improve it. "
            f"If you have a valid reason for your absences, please contact me.\n\n"
            f"Regards,\n{teacher_name}")
    return subject, body


def smtp_configured():
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def send_one(to_addr, subject, body):
    """Sends a single email. Raises on failure (the caller reports it per student)."""
    msg = EmailMessage()
    msg["From"] = _clean_line(config.SMTP_FROM)
    msg["To"] = _clean_line(to_addr)
    msg["Subject"] = _clean_line(subject)
    msg.set_content(body)
    if config.SMTP_TLS == "ssl":
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
    try:
        if config.SMTP_TLS == "starttls":
            server.starttls(context=ssl.create_default_context())
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


SYNC = False          # tests set this to True so mails are "sent" before the request returns


def send_in_background(to_addr, subject, body):
    """Sends without making the web request wait for the mail server. Failures are only logged."""
    import logging
    import threading

    def work():
        try:
            send_one(to_addr, subject, body)
        except Exception:
            logging.getLogger("quickmark.mail").exception("could not send email")
    if SYNC:
        work()
    else:
        threading.Thread(target=work, daemon=True).start()


def reset_code_message(name_or_email, code):
    subject = "QuickMark password reset code"
    body = (f"Hello,\n\nYour QuickMark password reset code is: {code}\n\n"
            f"It works for 15 minutes. If you did not ask for it, ignore this email - your password has not changed.\n\nQuickMark")
    return subject, body
