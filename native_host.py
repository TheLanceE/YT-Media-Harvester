"""Chrome native messaging host: the helper the extension talks to.

  python native_host.py install     register with Chrome (run once, via install.bat)
  python native_host.py uninstall   remove the registration

Chrome itself runs it through native_host.bat when the extension's background worker connects, and keeps it
running while the port is open. Messages are JSON, each prefixed with its length (4 bytes, native byte order).

Requests  {id, cmd, ...}  ->  replies {id, ok: true, ...} or {id, ok: false, error}
  hello                         {version, out_dir, default_out_dir}
  config        [out_dir]       read, or set (empty resets to the default)
  choose_folder                 OS folder picker; {out_dir} or {cancelled: true}
  open                          show the download folder
  download      url, format     {job}
  jobs                          {jobs: {id: job}}
Events    {event: "job", job: id, ...job fields}   sent whenever a job's state changes
"""
import json
import os
import struct
import sys
import threading
import time

NAME = "com.yt_tab_downloader.helper"
EXTENSION_ID = "kcnffalmlnicdbnolfbgonjbjaekcleg"  # pinned by "key" in extension/manifest.json
BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, f"{NAME}.json")
REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{NAME}"
LOG = os.path.join(BASE, "helper.log")
LOG_MAX_BYTES = 1024 * 1024  # helper.log starts over once it grows past this
MAX_MESSAGE = 1024 * 1024  # Chrome's own limit for messages to the extension
POLL_SECONDS = 0.5


class Channel:
    """Reads requests from Chrome and writes replies and events back. Only this class touches the real stdout."""

    def __init__(self, inp, out):
        self.inp, self.out, self.lock = inp, out, threading.Lock()

    def read(self):
        raw = self.inp.read(4)
        if len(raw) < 4:
            return None
        length = struct.unpack("=I", raw)[0]
        if length > MAX_MESSAGE:
            return None
        data = self.inp.read(length)
        return json.loads(data) if len(data) == length else None

    def send(self, msg: dict):
        data = json.dumps(msg).encode()
        with self.lock:
            self.out.write(struct.pack("=I", len(data)) + data)
            self.out.flush()


def version() -> str:
    try:
        with open(os.path.join(BASE, "extension", "manifest.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return ""


def handle(msg: dict) -> dict:
    """Run one request and return the reply's fields. Raises ValueError for a bad request."""
    import core

    cmd = msg.get("cmd")
    if cmd == "hello":
        return {"version": version(), "out_dir": core.out_dir(), "default_out_dir": core.DEFAULT_OUT_DIR}
    if cmd == "config":
        if "out_dir" in msg:
            if not isinstance(msg["out_dir"], str):
                raise ValueError("out_dir must be a string")
            core.set_out_dir(msg["out_dir"])
        return {"out_dir": core.out_dir(), "default_out_dir": core.DEFAULT_OUT_DIR}
    if cmd == "choose_folder":
        try:
            picked = core.choose_folder()
        except ImportError as e:
            raise ValueError("folder picker unavailable (no tkinter); type the path instead") from e
        if not picked:
            return {"cancelled": True, "out_dir": core.out_dir()}
        return {"out_dir": core.set_out_dir(picked)}
    if cmd == "open":
        core.open_folder()
        return {}
    if cmd == "download":
        return {"job": core.start_job(msg.get("url", ""), msg.get("format", "mp3"))}
    if cmd == "jobs":
        core.prune_jobs()
        return {"jobs": core.jobs}
    raise ValueError(f"unknown command: {cmd!r}")


def answer(channel: Channel, msg: dict):
    reply = {"id": msg.get("id")}
    try:
        reply.update(ok=True, **handle(msg))
    except ValueError as e:
        reply.update(ok=False, error=str(e))
    except Exception as e:  # noqa: BLE001 - report anything to the extension rather than dying silently
        reply.update(ok=False, error=f"helper error: {e}")
    channel.send(reply)


def watch_jobs(channel: Channel, stop: threading.Event):
    """Send a job event whenever a job's state changes."""
    import core

    seen: dict[str, str] = {}
    while not stop.wait(POLL_SECONDS):
        for job_id, job in list(core.jobs.items()):
            state = json.dumps(job, sort_keys=True)
            if seen.get(job_id) != state:
                seen[job_id] = state
                channel.send({"event": "job", "job": job_id, **job})


def isolate_stdout():
    """Keep the real stdout for messages only. yt-dlp, ffmpeg and print() would corrupt the stream,
    so everything else that writes to fd 1 or 2 goes to helper.log instead."""
    out = os.fdopen(os.dup(1), "wb")
    big = os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX_BYTES
    log = open(LOG, "wb" if big else "ab")
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    sys.stdout = sys.stderr = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
    return out


def serve(inp, out):
    channel = Channel(inp, out)
    stop = threading.Event()
    threading.Thread(target=watch_jobs, args=(channel, stop), daemon=True).start()
    while (msg := channel.read()) is not None:
        if isinstance(msg, dict):
            # Each request in its own thread: the folder picker blocks until the user closes it.
            threading.Thread(target=answer, args=(channel, msg), daemon=True).start()
    # Chrome closed the port (browser quit or the extension let go): don't leave half-written files behind.
    import core

    stop.set()
    for job_id, job in list(core.jobs.items()):
        if job["status"] == "running":
            core.remove_partials(job_id)


def install():
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({
            "name": NAME,
            "description": "YT Media Harvester helper",
            "path": os.path.join(BASE, "native_host.bat"),
            "type": "stdio",
            "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
        }, f, indent=2)
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValue(k, "", winreg.REG_SZ, MANIFEST)
    print(f"Registered {NAME} -> {MANIFEST}")


def uninstall():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        pass
    if os.path.exists(MANIFEST):
        os.remove(MANIFEST)
    print(f"Removed {NAME}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["install"]:
        install()
    elif sys.argv[1:2] == ["uninstall"]:
        uninstall()
    else:  # launched by Chrome; argv[1] is the caller's origin
        if os.name == "nt":
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        out = isolate_stdout()
        print(f"--- host started {time.strftime('%Y-%m-%d %H:%M:%S')}")
        serve(sys.stdin.buffer, out)
        sys.stdout.flush()
        os._exit(0)  # don't wait for download threads: Chrome has gone
