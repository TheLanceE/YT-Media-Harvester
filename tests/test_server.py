"""Unit tests for the helper's request checks. yt-dlp is never asked to download anything."""
import http.client
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    cfg = tmp_path_factory.mktemp("cfg") / "config.json"
    auth.CONFIG = str(cfg)  # keep the developer's real config.json untouched
    import server as srv

    srv.CONFIG = str(cfg)
    srv.auth_token = auth.token()
    srv._real_run_job = srv.run_job
    srv.run_job = lambda *a: None  # requests never start a real download
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield srv, httpd.server_address[1]
    httpd.shutdown()


def request(port, method, path, body=None, headers=None, token=True, srv=None):
    h = {"Host": f"127.0.0.1:{srv.PORT}", "Origin": auth.ORIGIN}
    if token:
        h[auth.HEADER] = srv.auth_token
    h.update(headers or {})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    conn.request(method, path, body=data, headers={k: v for k, v in h.items() if v is not None})
    r = conn.getresponse()
    return r.status, json.loads(r.read() or b"{}")


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL1",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/abc123",
    "https://youtu.be/dQw4w9WgXcQ",
])
def test_youtube_urls_allowed(server, url):
    srv, _ = server
    assert srv.is_youtube_video(url)


@pytest.mark.parametrize("url", [
    "https://evil.example/?x=youtube.com/watch",
    "https://evil.example/youtu.be/abc",
    "https://youtube.com.evil.example/watch?v=x",
    "https://www.youtube.com@evil.example/watch?v=x",
    "https://user@www.youtube.com/watch?v=x",
    "https://www.youtube.com:8080/watch?v=x",
    "file:///C:/Windows/youtube.com/watch",
    "https://www.youtube.com/watch",
    "https://www.youtube.com/channel/UC123",
    "https://youtu.be/",
    "http://[::1/watch",
    "",
])
def test_other_urls_rejected(server, url):
    srv, _ = server
    assert not srv.is_youtube_video(url)


def test_percent_from_bytes(server):
    srv, _ = server
    assert srv.percent({"downloaded_bytes": 50, "total_bytes": 200}) == "25.0%"
    assert srv.percent({"downloaded_bytes": 50, "total_bytes_estimate": 100}) == "50.0%"
    assert srv.percent({"downloaded_bytes": 50}) == ""


def test_prune_drops_only_old_finished_jobs(server):
    srv, _ = server
    srv.jobs.update(old={"status": "done", "finished_at": 0.0}, new={"status": "done", "finished_at": 1000.0},
                    running={"status": "running"})
    srv.prune_jobs(now=1000.0 + 1)
    assert "old" not in srv.jobs and "new" in srv.jobs and "running" in srv.jobs
    srv.jobs.clear()


def test_requires_token(server):
    srv, port = server
    assert request(port, "GET", "/", token=False, srv=srv)[0] == 401


def test_rejects_foreign_origin(server):
    srv, port = server
    assert request(port, "GET", "/", headers={"Origin": "https://evil.example"}, srv=srv)[0] == 401


def test_rejects_rebound_host(server):
    srv, port = server
    assert request(port, "GET", "/", headers={"Host": "evil.example:8765"}, srv=srv)[0] == 401
    assert request(port, "OPTIONS", "/", headers={"Host": "evil.example:8765"}, token=False, srv=srv)[0] == 403


def test_preflight_only_for_extension(server):
    srv, port = server
    assert request(port, "OPTIONS", "/download", token=False, srv=srv)[0] == 204
    assert request(port, "OPTIONS", "/download", headers={"Origin": "https://evil.example"}, token=False, srv=srv)[0] == 403


def test_status_ok_with_token(server):
    srv, port = server
    status, body = request(port, "GET", "/", srv=srv)
    assert status == 200 and body["ok"]


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b'"text"'])
def test_bad_body_is_400(server, body):
    srv, port = server
    assert request(port, "POST", "/download", body=body, srv=srv)[0] == 400


def test_oversized_body_is_400(server):
    srv, port = server
    status, _ = request(port, "POST", "/download", body=b"{}", headers={"Content-Length": str(10**9)}, srv=srv)
    assert status == 400


def test_download_rejects_non_youtube(server):
    srv, port = server
    status, body = request(port, "POST", "/download", {"url": "https://evil.example/?x=youtube.com/watch"}, srv=srv)
    assert status == 400 and "YouTube" in body["error"]


def test_download_accepts_youtube(server, tmp_path):
    srv, port = server
    srv.set_out_dir(str(tmp_path))
    status, body = request(port, "POST", "/download", {"url": "https://youtu.be/dQw4w9WgXcQ", "format": "mp4"}, srv=srv)
    assert status == 202 and len(body["job"]) == 32
    srv.set_out_dir("")


def test_set_out_dir_rejects_unwritable(server, tmp_path):
    srv, _ = server
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(ValueError):
        srv.set_out_dir(str(blocker / "sub"))


def fake_ydl(errors):
    """A YoutubeDL stand-in whose extract_info raises the next error in turn (None = success)."""
    calls = []

    class FakeYDL:
        def __init__(self, opts):
            calls.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            err = errors[len(calls) - 1]
            if err:
                raise Exception(err)
            return {"title": "ok"}

    return FakeYDL, calls


def run_real_job(srv, monkeypatch, errors, tmp_path):
    ydl, calls = fake_ydl(errors)
    monkeypatch.setattr(srv, "YoutubeDL", ydl)
    srv.jobs["j"] = {"status": "running"}
    srv._real_run_job("j", "https://youtu.be/x", "mp3", str(tmp_path))
    return srv.jobs.pop("j"), calls


def test_cookie_failure_explained(server, monkeypatch, tmp_path):
    srv, _ = server
    errors = ["HTTP Error 403"] * 4 + ["Failed to decrypt cookie with DPAPI"]
    job, calls = run_real_job(srv, monkeypatch, errors, tmp_path)
    assert len(calls) == 5 and "cookiesfrombrowser" in calls[-1]
    assert job["status"] == "error" and job["error"].startswith("HTTP Error 403") and "cookies.txt" in job["error"]


def test_cookies_file_used_when_set(server, monkeypatch, tmp_path):
    srv, _ = server
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(srv, "load_config", lambda: {"cookies_file": str(cookies)})
    job, calls = run_real_job(srv, monkeypatch, ["HTTP Error 403"] * 4 + [None], tmp_path)
    assert job["status"] == "done" and calls[-1]["cookiefile"] == str(cookies)


def test_non_403_error_stops_retrying(server, monkeypatch, tmp_path):
    srv, _ = server
    job, calls = run_real_job(srv, monkeypatch, ["Video unavailable"], tmp_path)
    assert len(calls) == 1 and job["error"] == "Video unavailable"
