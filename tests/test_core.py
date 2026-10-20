"""Unit tests for core.py, the download engine. yt-dlp is never asked to download anything."""
import pytest

import core as _core

REAL_RUN_JOB = _core.run_job  # the fixture stubs core.run_job; these tests call the real one


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL1",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/abc123",
    "https://youtu.be/dQw4w9WgXcQ",
])
def test_youtube_urls_allowed(core, url):
    assert core.is_youtube_video(url)


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
def test_other_urls_rejected(core, url):
    assert not core.is_youtube_video(url)


def test_percent_from_bytes(core):
    assert core.percent({"downloaded_bytes": 50, "total_bytes": 200}) == "25.0%"
    assert core.percent({"downloaded_bytes": 50, "total_bytes_estimate": 100}) == "50.0%"
    assert core.percent({"downloaded_bytes": 50}) == ""


def test_prune_drops_only_old_finished_jobs(core):
    core.jobs.update(old={"status": "done", "finished_at": 0.0}, new={"status": "done", "finished_at": 1000.0},
                    running={"status": "running"})
    core.prune_jobs(now=1000.0 + 1)
    assert "old" not in core.jobs and "new" in core.jobs and "running" in core.jobs
    core.jobs.clear()


def test_set_out_dir_rejects_unwritable(core, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(ValueError):
        core.set_out_dir(str(blocker / "sub"))


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


def run_real_job(core, monkeypatch, errors, tmp_path):
    ydl, calls = fake_ydl(errors)
    monkeypatch.setattr(core, "YoutubeDL", ydl)
    core.jobs["j"] = {"status": "running"}
    REAL_RUN_JOB("j", "https://youtu.be/x", "mp3", str(tmp_path))
    return core.jobs.pop("j"), calls


def test_cookie_failure_explained(core, monkeypatch, tmp_path):
    errors = ["HTTP Error 403"] * 4 + ["Failed to decrypt cookie with DPAPI"]
    job, calls = run_real_job(core, monkeypatch, errors, tmp_path)
    assert len(calls) == 5 and "cookiesfrombrowser" in calls[-1]
    assert job["status"] == "error" and job["error"].startswith("HTTP Error 403") and "cookies.txt" in job["error"]


def test_chrome_decrypt_failure_explained(core, monkeypatch, tmp_path):
    job, calls = run_real_job(core, monkeypatch, [BOT, "Failed to decrypt with DPAPI"], tmp_path)
    assert job["error"].endswith(core.COOKIE_HINT)


def test_cookies_file_used_when_set(core, monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(core, "load_config", lambda: {"cookies_file": str(cookies)})
    job, calls = run_real_job(core, monkeypatch, ["HTTP Error 403"] * 4 + [None], tmp_path)
    assert job["status"] == "done" and calls[-1]["cookiefile"] == str(cookies)


BOT = "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies"


def test_bot_check_jumps_to_cookies(core, monkeypatch, tmp_path):
    job, calls = run_real_job(core, monkeypatch, [BOT, None], tmp_path)
    assert job["status"] == "done" and len(calls) == 2 and "cookiesfrombrowser" in calls[-1]


def test_bot_check_failure_explained(core, monkeypatch, tmp_path):
    job, calls = run_real_job(core, monkeypatch, [BOT, BOT], tmp_path)
    assert len(calls) == 2 and job["error"].startswith(BOT) and "cookies_file" in job["error"]


def test_non_403_error_stops_retrying(core, monkeypatch, tmp_path):
    job, calls = run_real_job(core, monkeypatch, ["Video unavailable"], tmp_path)
    assert len(calls) == 1 and job["error"] == "Video unavailable"


def test_start_job_validates_and_records(core):
    with pytest.raises(ValueError, match="YouTube"):
        core.start_job("https://evil.example/?x=youtube.com/watch", "mp3")
    with pytest.raises(ValueError, match="format"):
        core.start_job("https://youtu.be/x", "flac")
    job_id = core.start_job("https://youtu.be/dQw4w9WgXcQ", "mp4")
    job = core.jobs[job_id]
    assert len(job_id) == 32 and job["status"] == "running" and job["url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert job["format"] == "mp4" and core.busy()


def test_remove_partials_cleans_streams_outputs_and_cover(core, tmp_path):
    stem = tmp_path / "Song [abc]"
    files = [f"{stem}.f137.mp4.part", f"{stem}.f140.m4a", f"{stem}.webp", f"{stem}.temp.mp4"]
    for f in files:
        open(f, "w").close()
    keep = tmp_path / "Other [xyz].mp4"
    keep.write_text("x")
    core.jobs["j"] = {"status": "running", "format": "mp4"}
    core.partials["j"] = {f"{stem}.f137.mp4", f"{stem}.f140.m4a"}
    core.remove_partials("j")
    assert not any(tmp_path.joinpath(f).exists() for f in files) and keep.exists()


def test_finished_job_forgets_its_files(core, monkeypatch, tmp_path):
    job, _ = run_real_job(core, monkeypatch, [None], tmp_path)
    assert job["status"] == "done" and "j" not in core.partials
