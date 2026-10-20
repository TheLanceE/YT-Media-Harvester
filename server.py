"""Local helper: receives a YouTube URL from the browser extension and downloads it with yt-dlp."""
import hmac
import json
import os
import shutil
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL

import auth

# deno.exe crashes on this machine (0xc0000142) and yt-dlp probes it via PATH; hide it from this process.
os.environ["PATH"] = os.pathsep.join(
    d for d in os.environ.get("PATH", "").split(os.pathsep) if not os.path.exists(os.path.join(d, "deno.exe"))
)

HOST, PORT = "127.0.0.1", 8765
BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_DIR = os.path.join(BASE, "downloads")
CONFIG = auth.CONFIG  # {"out_dir": "D:\\Music"}; written by the extension's Settings page
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}  # anything else is DNS rebinding
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
JOB_TTL = 600  # seconds a finished job's status stays available
MAX_BODY = 64 * 1024
picker_lock = threading.Lock()


def load_config() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def out_dir() -> str:
    return load_config().get("out_dir") or DEFAULT_OUT_DIR


def set_out_dir(path: str) -> str:
    """Validate, create and save the download folder. Empty path resets to the default. Raises ValueError."""
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path.strip()))) if path.strip() else DEFAULT_OUT_DIR
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise ValueError(f"can't create folder: {e.strerror or e}") from e
    if not os.access(path, os.W_OK):
        raise ValueError("folder is not writable")
    cfg = load_config()
    cfg["out_dir"] = "" if path == DEFAULT_OUT_DIR else path
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


def choose_folder() -> str:
    """Show the OS folder picker on this machine. Returns "" if cancelled."""
    import tkinter
    from tkinter import filedialog

    with picker_lock:  # one dialog at a time
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)  # otherwise it opens behind Chrome
        try:
            picked = filedialog.askdirectory(parent=root, initialdir=out_dir(), title="Choose download folder")
        finally:
            root.destroy()
    return os.path.normpath(picked) if picked else ""


auth_token = auth.token()
jobs: dict[str, dict] = {}
last_request = time.monotonic()


def is_youtube_video(url: str) -> bool:
    """A watch, shorts or youtu.be link on a real YouTube host; substring checks let other sites through."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or parts.username or parts.password or parts.port not in (None, 80, 443):
        return False
    if host == "youtu.be":
        return len(parts.path.strip("/")) > 0
    if host in YOUTUBE_HOSTS:
        return (parts.path == "/watch" and "v=" in parts.query) or parts.path.startswith("/shorts/")
    return False


def percent(d: dict) -> str:
    """Progress as "42.0%" from byte counts; yt-dlp's _percent_str can carry ANSI colour codes."""
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    if not total:
        return ""
    return f"{min(100.0, 100.0 * (d.get('downloaded_bytes') or 0) / total):.1f}%"


def prune_jobs(now: float | None = None):
    now = time.monotonic() if now is None else now
    for job_id, job in list(jobs.items()):
        if job.get("finished_at") is not None and now - job["finished_at"] > JOB_TTL:
            jobs.pop(job_id, None)


def ydl_opts(fmt: str, job_id: str, dest: str) -> dict:
    def hook(d):
        job = jobs[job_id]
        if d["status"] == "downloading":
            job["progress"] = percent(d)
        elif d["status"] == "finished":
            # MP4s are fetched as two streams (video, then audio); "part" lets the popup say which one.
            job["part"] = job.get("part", 1) + 1
            job["progress"] = "converting"

    opts = {
        "outtmpl": os.path.join(dest, "%(title)s [%(id)s].%(ext)s"),  # the id keeps same-titled videos apart
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "writethumbnail": True,  # downloaded, embedded as cover art, then deleted
    }
    # Use Node for YouTube's JS challenge.
    node = shutil.which("node")
    if node:
        opts["js_runtimes"] = {"node": {"path": node}}
    # Tags (title, artist = channel, date, description, URL) and the thumbnail as cover art.
    # YouTube thumbnails are often webp, which MP3/MP4 can't embed, so convert to jpg first.
    tagging = [
        {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": fmt == "mp4"},
        {"key": "EmbedThumbnail"},
    ]
    if fmt == "mp3":
        opts.update(
            format="bestaudio/best",
            postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}, *tagging],
        )
    else:
        opts.update(
            format="bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", merge_output_format="mp4", postprocessors=tagging
        )
    return opts


COOKIE_HINT = (
    "Retrying with your Chrome cookies didn't work either: Chrome 127+ on Windows locks them while Chrome is open. "
    'Export a cookies.txt for youtube.com and set "cookies_file" to its path in config.json.'
)


def cookie_attempt() -> dict:
    """The last retry rung: a cookies.txt from config.json if one is set, else Chrome's own cookie store."""
    path = load_config().get("cookies_file") or ""
    if path and os.path.isfile(path):
        return {"cookiefile": path}
    return {"cookiesfrombrowser": ("chrome",)}


def run_job(job_id: str, url: str, fmt: str, dest: str):
    # On 403, retry with other YouTube player clients, then with cookies.
    attempts = [
        {},
        {},  # plain retry: "page needs to be reloaded" is usually transient
        {"extractor_args": {"youtube": {"player_client": ["tv", "web_safari"]}}},
        {"extractor_args": {"youtube": {"player_client": ["android_vr", "mweb"]}}},
        cookie_attempt(),
    ]
    first_err = ""
    for extra in attempts:
        try:
            with YoutubeDL({**ydl_opts(fmt, job_id, dest), **extra}) as ydl:
                info = ydl.extract_info(url, download=True)
            jobs[job_id].update(status="done", title=info.get("title"), progress="100%", finished_at=time.monotonic())
            return
        except Exception as e:  # noqa: BLE001
            first_err = first_err or str(e)
            if "cookiesfrombrowser" in extra and "cookie" in str(e).lower():
                # Reading Chrome's cookies failed, which says nothing about the video; explain instead of hiding it.
                first_err = f"{first_err} {COOKIE_HINT}"
            if "403" not in str(e) and "reloaded" not in str(e):
                break
    jobs[job_id].update(status="error", error=first_err, finished_at=time.monotonic())


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
        prune_jobs()
        if self.path.startswith("/status/"):
            job = jobs.get(self.path.rsplit("/", 1)[1])
            return self._send(200 if job else 404, job or {"error": "unknown job"})
        if self.path == "/open":
            os.makedirs(out_dir(), exist_ok=True)
            os.startfile(out_dir())
        self._send(200, {"ok": True, "out_dir": out_dir(), "default_out_dir": DEFAULT_OUT_DIR})

    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        body = self._json_body()
        if body is None:
            return self._send(400, {"error": "request body must be a JSON object"})
        if self.path in ("/config", "/choose-folder"):
            try:
                if self.path == "/choose-folder":
                    picked = choose_folder()
                    if not picked:
                        return self._send(200, {"ok": False, "cancelled": True, "out_dir": out_dir()})
                    body = {"out_dir": picked}
                return self._send(200, {"ok": True, "out_dir": set_out_dir(body.get("out_dir", ""))})
            except ImportError:
                return self._send(500, {"error": "folder picker unavailable (no tkinter); type the path instead"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
        if self.path != "/download":
            return self._send(404, {"error": "not found"})
        url, fmt = body.get("url", ""), body.get("format", "mp3")
        if not isinstance(url, str) or not is_youtube_video(url):
            return self._send(400, {"error": "not a YouTube video URL"})
        if fmt not in ("mp3", "mp4"):
            return self._send(400, {"error": "format must be mp3 or mp4"})
        prune_jobs()
        job_id = uuid.uuid4().hex
        dest = out_dir()
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError:
            return self._send(400, {"error": f"download folder unavailable: {dest}. Change it in Settings."})
        jobs[job_id] = {"status": "running", "progress": "0%", "out_dir": dest}
        threading.Thread(target=run_job, args=(job_id, url, fmt, dest), daemon=True).start()
        self._send(202, {"job": job_id})

    def log_message(self, *_):
        pass


def exit_when_idle(minutes: float):
    # Started by the extension (native_host.py): stop once nothing has happened for a while.
    while True:
        time.sleep(30)
        busy = any(j["status"] == "running" for j in jobs.values())
        if not busy and time.monotonic() - last_request > minutes * 60:
            os._exit(0)


if __name__ == "__main__":
    import yt_dlp
    print(f"yt-dlp {yt_dlp.version.__version__} via {sys.executable}")
    if "--idle-minutes" in sys.argv:
        minutes = float(sys.argv[sys.argv.index("--idle-minutes") + 1])
        threading.Thread(target=exit_when_idle, args=(minutes,), daemon=True).start()
    print(f"Listening on http://{HOST}:{PORT}  ->  saving to {out_dir()}", flush=True)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
