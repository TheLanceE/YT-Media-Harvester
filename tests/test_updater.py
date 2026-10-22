"""The installed build's yt-dlp updater, with PyPI faked: nothing is downloaded."""
import hashlib
import io
import json
import zipfile

import pytest

import updater


def wheel(version: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("yt_dlp/__init__.py", "")
        z.writestr("yt_dlp/version.py", f"__version__ = '{version}'\n")
        z.writestr(f"yt_dlp-{version}.dist-info/METADATA", "")
    return buf.getvalue()


@pytest.fixture
def pypi(monkeypatch):
    """Serve one release from a fake PyPI; returns a dict to change what it serves."""
    served = {"version": "2026.10.21", "wheel": wheel("2026.10.21"), "sha256": None}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(url, timeout):
        if url == updater.PYPI:
            sha = served["sha256"] or hashlib.sha256(served["wheel"]).hexdigest()
            return Response(json.dumps({"info": {"version": served["version"]}, "urls": [
                {"packagetype": "sdist", "filename": "yt_dlp.tar.gz", "url": "x", "digests": {"sha256": ""}},
                {"packagetype": "bdist_wheel", "filename": "yt_dlp-py3-none-any.whl", "url": "wheel",
                 "digests": {"sha256": sha}},
            ]}).encode())
        assert url == "wheel"
        return Response(served["wheel"])

    monkeypatch.setattr(updater.urllib.request, "urlopen", urlopen)
    return served


def test_installs_newer_release_into_lib(pypi, tmp_path):
    assert updater.update(str(tmp_path), "2026.08.19") == "2026.10.21"
    assert updater.installed_version(str(tmp_path / "lib")) == "2026.10.21"
    assert sorted(p.name for p in (tmp_path / "lib").iterdir()) == ["yt_dlp"]  # only the package, no dist-info
    assert not (tmp_path / "lib.new").exists() and not (tmp_path / "lib.old").exists()


def test_replaces_an_older_update(pypi, tmp_path):
    updater.update(str(tmp_path), "2026.08.19")
    pypi.update(version="2026.11.2", wheel=wheel("2026.11.2"))
    updater.update(str(tmp_path), "2026.10.21")
    assert updater.installed_version(str(tmp_path / "lib")) == "2026.11.2"


def test_leaves_lib_alone_when_current(pypi, tmp_path):
    assert updater.update(str(tmp_path), "2026.10.21") == "2026.10.21"
    assert not (tmp_path / "lib").exists()
    assert updater.load_state(str(tmp_path))["checked"] > 0


def test_skips_a_version_that_failed_to_load(pypi, tmp_path):
    updater.save_state(str(tmp_path), skip="2026.10.21")
    updater.update(str(tmp_path), "2026.08.19")
    assert not (tmp_path / "lib").exists()


def test_rejects_checksum_mismatch(pypi, tmp_path):
    pypi["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="checksum"):
        updater.update(str(tmp_path), "2026.08.19")
    assert not (tmp_path / "lib").exists()


def test_daily_check_runs_once_a_day(pypi, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "update", lambda base, current: calls.append(current) or current)
    updater.check_daily(str(tmp_path), "2026.08.19")
    updater.save_state(str(tmp_path), checked=updater.time.time())
    updater.check_daily(str(tmp_path), "2026.08.19")
    assert calls == ["2026.08.19"]


def test_version_order_ignores_leading_zeros():
    assert updater.vtuple("2026.08.19") == updater.vtuple("2026.8.19") < updater.vtuple("2026.10.1")
