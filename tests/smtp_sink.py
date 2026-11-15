"""A tiny fake mail server for tests: accepts emails and keeps them in a list (nothing leaves your computer)."""
import email
import socket
import threading


class SmtpSink:
    def __init__(self):
        self.messages = []                                  # parsed email.message.Message objects
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        f = conn.makefile("rwb")
        def say(line): f.write((line + "\r\n").encode()); f.flush()
        say("220 sink ready")
        data_mode, buf = False, []
        while True:
            line = f.readline()
            if not line:
                break
            if data_mode:
                if line == b".\r\n":
                    self.messages.append(email.message_from_bytes(b"".join(buf))); data_mode, buf = False, []; say("250 queued")
                else:
                    buf.append(line[1:] if line.startswith(b"..") else line)
                continue
            cmd = line.decode(errors="replace").strip().upper()
            if cmd.startswith(("EHLO", "HELO")): say("250 sink")
            elif cmd.startswith(("MAIL", "RCPT", "RSET", "NOOP")): say("250 OK")
            elif cmd.startswith("DATA"): data_mode = True; say("354 go ahead")
            elif cmd.startswith("QUIT"): say("221 bye"); break
            else: say("502 not supported")
        conn.close()

    def close(self):
        self._stop = True; self.srv.close()
