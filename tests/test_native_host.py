"""The native messaging host: its commands, the framing Chrome uses, and that stdout carries only messages."""
import json
import os
import struct
import subprocess
import sys
import threading
import time

import native_host

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame(msg: dict) -> bytes:
    data = json.dumps(msg).encode()
    return struct.pack("=I", len(data)) + data


def unframe(stream) -> dict:
    length = struct.unpack("=I", stream.read(4))[0]
    return json.loads(stream.read(length))


def test_hello_and_config(core, tmp_path):
    hello = native_host.handle({"cmd": "hello"})
    assert hello["out_dir"] == core.DEFAULT_OUT_DIR and hello["version"]
    set_reply = native_host.handle({"cmd": "config", "out_dir": str(tmp_path / "music")})
    assert set_reply["out_dir"] == str(tmp_path / "music")
    assert native_host.handle({"cmd": "config"})["out_dir"] == str(tmp_path / "music")


def test_download_and_jobs(core):
    job = native_host.handle({"cmd": "download", "url": "https://youtu.be/dQw4w9WgXcQ", "format": "mp3"})["job"]
    assert job in native_host.handle({"cmd": "jobs"})["jobs"]


def test_bad_requests_get_error_replies(core):
    sent = []

    class Fake:
        send = sent.append

    native_host.answer(Fake, {"id": 1, "cmd": "download", "url": "https://evil.example/?youtube.com/watch"})
    native_host.answer(Fake, {"id": 2, "cmd": "nope"})
    native_host.answer(Fake, {"id": 3, "cmd": "config", "out_dir": 5})
    native_host.answer(Fake, {"id": 4, "cmd": "update_ytdlp"})  # a source checkout updates through install.bat
    assert [m["id"] for m in sent] == [1, 2, 3, 4] and not any(m["ok"] for m in sent)
    assert "YouTube" in sent[0]["error"] and "unknown command" in sent[1]["error"] and "install.bat" in sent[3]["error"]


def test_job_events_follow_changes(core):
    sent = []

    class Fake:
        send = sent.append

    stop = threading.Event()
    core.jobs["j"] = {"status": "running", "progress": "10.0%"}
    t = threading.Thread(target=native_host.watch_jobs, args=(Fake, stop))
    t.start()
    time.sleep(native_host.POLL_SECONDS * 2.5)
    core.jobs["j"]["progress"] = "55.0%"
    time.sleep(native_host.POLL_SECONDS * 2.5)
    stop.set()
    t.join()
    progress = [m["progress"] for m in sent if m.get("event") == "job" and m["job"] == "j"]
    assert progress == ["10.0%", "55.0%"]  # one event per change, none while nothing changed


def test_framing_end_to_end(tmp_path):
    """Run the host the way Chrome does and check that stdout holds nothing but framed replies."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "native_host.py"), "chrome-extension://test/"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=tmp_path, env=env)
    p.stdin.write(frame({"id": 7, "cmd": "hello"}) + frame({"id": 8, "cmd": "nope"}))
    p.stdin.flush()
    replies = {m["id"]: m for m in (unframe(p.stdout), unframe(p.stdout))}
    p.stdin.close()
    assert p.wait(timeout=30) == 0
    assert p.stdout.read() == b""  # print() and library output went to helper.log, not to Chrome
    assert replies[7]["ok"] and "out_dir" in replies[7]
    assert not replies[8]["ok"]
