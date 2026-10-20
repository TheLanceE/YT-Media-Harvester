"""Local helper, HTTP transport: the extension talks to it on 127.0.0.1:8765. The work is done in core.py."""
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import auth
import core

HOST, PORT = "127.0.0.1", 8765
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}  # anything else is DNS rebinding
MAX_BODY = 64 * 1024

auth_token = auth.token()
last_request = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        global last_request
        last_request = time.monotonic()
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", auth.ORIGIN)
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {auth.HEADER}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        """Only the extension, reached as localhost (a rebound DNS name sends its own Host),
        with its own origin (or none, which Chrome may omit for extension pages) and the token.
        A web page can't send the token header without a CORS preflight, which only allows our origin."""
        if self.headers.get("Host", "").lower() not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != auth.ORIGIN:
            return False
        return hmac.compare_digest(self.headers.get(auth.HEADER, "").encode(), auth_token.encode())

    def do_OPTIONS(self):
        ok = self.headers.get("Origin") == auth.ORIGIN and self.headers.get("Host", "").lower() in ALLOWED_HOSTS
        self._send(204 if ok else 403, {})

    def _json_body(self) -> dict | None:
        """The request body as a JSON object, or None if it is missing, too big or not valid JSON."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= MAX_BODY:
                return None
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return None
        return body if isinstance(body, dict) else None

    def do_GET(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        core.prune_jobs()
        if self.path.startswith("/status/"):
            job = core.jobs.get(self.path.rsplit("/", 1)[1])
            return self._send(200 if job else 404, job or {"error": "unknown job"})
        if self.path == "/open":
            core.open_folder()
        self._send(200, {"ok": True, "out_dir": core.out_dir(), "default_out_dir": core.DEFAULT_OUT_DIR})

    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        body = self._json_body()
        if body is None:
            return self._send(400, {"error": "request body must be a JSON object"})
        if self.path in ("/config", "/choose-folder"):
            try:
                if self.path == "/choose-folder":
                    picked = core.choose_folder()
                    if not picked:
                        return self._send(200, {"ok": False, "cancelled": True, "out_dir": core.out_dir()})
                    body = {"out_dir": picked}
                return self._send(200, {"ok": True, "out_dir": core.set_out_dir(body.get("out_dir", ""))})
            except ImportError:
                return self._send(500, {"error": "folder picker unavailable (no tkinter); type the path instead"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
        if self.path != "/download":
            return self._send(404, {"error": "not found"})
        try:
            job_id = core.start_job(body.get("url", ""), body.get("format", "mp3"))
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        self._send(202, {"job": job_id})

    def log_message(self, *_):
        pass


def exit_when_idle(minutes: float):
    # Started by the extension (native_host.py): stop once nothing has happened for a while.
    while True:
        time.sleep(30)
        if not core.busy() and time.monotonic() - last_request > minutes * 60:
            os._exit(0)


if __name__ == "__main__":
    import yt_dlp
    print(f"yt-dlp {yt_dlp.version.__version__} via {sys.executable}")
    if "--idle-minutes" in sys.argv:
        minutes = float(sys.argv[sys.argv.index("--idle-minutes") + 1])
        threading.Thread(target=exit_when_idle, args=(minutes,), daemon=True).start()
    print(f"Listening on http://{HOST}:{PORT}  ->  saving to {core.out_dir()}", flush=True)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
