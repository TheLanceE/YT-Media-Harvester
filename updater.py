"""Keeps yt-dlp current in the installed build, which can't pip-upgrade itself.

YouTube changes often and old yt-dlp releases stop working, so the helper checks PyPI at most once a day and unpacks
a newer yt-dlp wheel into lib/ next to the helper. activate() puts lib/ first on sys.path at startup, so the newer
copy wins over the one frozen into the build. A copy that fails to import is removed and its version skipped.

Nothing here imports yt_dlp at module level: activate() has to run before anything else does.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

PYPI = "https://pypi.org/pypi/yt-dlp/json"
CHECK_EVERY = 24 * 3600  # seconds between automatic checks
TIMEOUT = 30


def vtuple(version: str) -> tuple:
    """"2026.08.19" -> (2026, 8, 19); PyPI drops the leading zeros, yt-dlp's own __version__ keeps them."""
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def load_state(base: str) -> dict:
    try:
        with open(os.path.join(base, "updater.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(base: str, **changes):
    state = {**load_state(base), **changes}
    with open(os.path.join(base, "updater.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def activate(base: str):
    """Use the yt-dlp in lib/ if there is one. Call before anything imports yt_dlp."""
    lib = os.path.join(base, "lib")
    if not os.path.isdir(os.path.join(lib, "yt_dlp")):
        return
    sys.path.insert(0, lib)
    try:
        import yt_dlp.version  # noqa: F401
        from yt_dlp import YoutubeDL  # noqa: F401
    except Exception as e:  # noqa: BLE001 - any failure means: fall back to the bundled copy
        sys.path.remove(lib)
        for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
            del sys.modules[name]
        skipped = installed_version(lib)
        shutil.rmtree(lib, ignore_errors=True)
        save_state(base, skip=skipped)
        print(f"yt-dlp {skipped} in lib/ failed to load ({e}); using the bundled copy")


def installed_version(lib: str) -> str:
    """The version of the yt-dlp unpacked in lib/, read from its version.py without importing it."""
    try:
        with open(os.path.join(lib, "yt_dlp", "version.py"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def latest() -> tuple[str, str, str]:
    """(version, wheel URL, sha256) of the newest yt-dlp on PyPI."""
    with urllib.request.urlopen(PYPI, timeout=TIMEOUT) as r:
        data = json.load(r)
    for f in data["urls"]:
        if f["packagetype"] == "bdist_wheel" and f["filename"].endswith("-py3-none-any.whl"):
            return data["info"]["version"], f["url"], f["digests"]["sha256"]
    raise RuntimeError("PyPI lists no yt-dlp wheel")


def update(base: str, current: str) -> str:
    """Unpack the newest yt-dlp into lib/ if it's newer than `current`. Returns the newest version available.
    The running helper keeps its yt-dlp; the next helper start loads the new one."""
    version, url, sha256 = latest()
    save_state(base, checked=time.time())
    if vtuple(version) <= vtuple(current) or version == load_state(base).get("skip"):
        return version
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        wheel = r.read()
    if hashlib.sha256(wheel).hexdigest() != sha256:
        raise RuntimeError("downloaded yt-dlp wheel doesn't match PyPI's checksum")
    lib, new, old = (os.path.join(base, name) for name in ("lib", "lib.new", "lib.old"))
    shutil.rmtree(new, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(wheel)) as z:
        z.extractall(new, [n for n in z.namelist() if n.startswith("yt_dlp/")])
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(lib):
        os.rename(lib, old)
    os.rename(new, lib)
    shutil.rmtree(old, ignore_errors=True)
    return version


def check_daily(base: str, current: str):
    """The automatic check, run in the background when the helper starts."""
    if time.time() - load_state(base).get("checked", 0) < CHECK_EVERY:
        return
    try:
        print(f"yt-dlp update check: {current} -> {update(base, current)}")
    except Exception as e:  # noqa: BLE001 - offline or PyPI down: try again next start
        print(f"yt-dlp update check failed: {e}")
