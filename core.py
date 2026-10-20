"""Download engine shared by the helper's transports: config, URL checks, jobs and the yt-dlp pipeline.

No transport code lives here: native_host.py drives it over Chrome native messaging.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL

# deno.exe crashes on this machine (0xc0000142) and yt-dlp probes it via PATH; hide it from this process.
os.environ["PATH"] = os.pathsep.join(
    d for d in os.environ.get("PATH", "").split(os.pathsep) if not os.path.exists(os.path.join(d, "deno.exe"))
)

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_DIR = os.path.join(BASE, "downloads")
CONFIG = os.path.join(BASE, "config.json")  # {"out_dir": "D:\\Music"}; written by the extension's Settings page
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
JOB_TTL = 600  # seconds a finished job's status stays available
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


jobs: dict[str, dict] = {}
partials: dict[str, set[str]] = {}  # files a job has written so far, deleted if it is cut off mid-download


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
        partials.setdefault(job_id, set()).update(p for p in (d.get("tmpfilename"), d.get("filename")) if p)
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
            partials.pop(job_id, None)
            return
        except Exception as e:  # noqa: BLE001
            first_err = first_err or str(e)
            if "cookiesfrombrowser" in extra and "cookie" in str(e).lower():
                # Reading Chrome's cookies failed, which says nothing about the video; explain instead of hiding it.
                first_err = f"{first_err} {COOKIE_HINT}"
            if "403" not in str(e) and "reloaded" not in str(e):
                break
    jobs[job_id].update(status="error", error=first_err, finished_at=time.monotonic())
    partials.pop(job_id, None)


def start_job(url: str, fmt: str) -> str:
    """Validate a download request and start it in a thread. Returns the job id; raises ValueError for bad input."""
    if not isinstance(url, str) or not is_youtube_video(url):
        raise ValueError("not a YouTube video URL")
    if fmt not in ("mp3", "mp4"):
        raise ValueError("format must be mp3 or mp4")
    prune_jobs()
    dest = out_dir()
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        raise ValueError(f"download folder unavailable: {dest}. Change it in Settings.") from e
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "progress": "0%", "out_dir": dest, "url": url, "format": fmt, "started": time.time()}
    threading.Thread(target=run_job, args=(job_id, url, fmt, dest), daemon=True).start()
    return job_id


def remove_partials(job_id: str):
    """Delete what an unfinished job left behind (.part files, unmerged streams, a half-converted output)."""
    fmt = jobs.get(job_id, {}).get("format", "")
    for path in partials.pop(job_id, set()):
        # "Title [id].f137.mp4" is one stream of "Title [id].mp4"; ffmpeg writes "<out>.temp.<ext>" while converting.
        stem = re.sub(r"\.f\d+$", "", os.path.splitext(path)[0])
        outputs = [f"{stem}.{ext}" for ext in ("jpg", "webp", "png")]  # the cover art, until it is embedded
        if fmt:
            outputs += [f"{stem}.{fmt}", f"{stem}.temp.{fmt}"]
        for p in (path, path + ".part", path + ".ytdl", *outputs):
            try:
                os.remove(p)
            except OSError:
                pass


def busy() -> bool:
    return any(j["status"] == "running" for j in jobs.values())


def open_folder():
    """Show the download folder in the OS file manager."""
    path = out_dir()
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
