"""Build the Windows installer: freeze the helper, add ffmpeg and Deno, stage the extension, run Inno Setup.

  python scripts/build_installer.py [tag] [out_dir]     e.g. v0.4.0-beta dist
  python scripts/build_installer.py --stage-only        stop after build/stage (no Inno Setup needed)

Needs Windows, the packages in requirements-build.txt, and Inno Setup 6 (ISCC.exe on PATH, in its default folder,
or named by the ISCC environment variable). RELEASE_ROOT points it at another checkout, like build_release.py.

ffmpeg and Deno are downloaded once into build/tools and checked against the checksums their publishers release
next to them. Output: <out_dir>/YT-Media-Harvester-Setup-<tag>.exe.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.abspath(os.environ.get("RELEASE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(ROOT, "build")
STAGE = os.path.join(BUILD, "stage")
TOOLS = os.path.join(BUILD, "tools")
HELPER = "YTMediaHarvesterHelper"

# Pinned releases. The checksum files come from the same release as the archive.
FFMPEG = {
    "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-lgpl-8.1.zip",
    "sums": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256",
    "files": {"ffmpeg.exe": "bin/ffmpeg.exe", "ffprobe.exe": "bin/ffprobe.exe", "FFMPEG-LICENSE.txt": "LICENSE.txt"},
}
DENO = {
    "url": "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip",
    "sums": "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip.sha256sum",
    "files": {"deno.exe": "deno.exe"},
}


def manifest_version() -> tuple[str, str]:
    with open(os.path.join(ROOT, "extension", "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    return m["version"], m.get("version_name", m["version"])


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def expected_sha256(sums: str, archive: str) -> str:
    """The digest for `archive` in a checksum file: sha256sum lines ("<hex>  <name>"), or a file holding a single
    digest in any layout (Deno publishes PowerShell's Get-FileHash output)."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == archive and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    digests = re.findall(r"\b[0-9a-fA-F]{64}\b", sums)
    if len(digests) == 1:
        return digests[0].lower()
    sys.exit(f"no checksum for {archive}")


def tool_archive(spec: dict) -> str:
    """Download (once) and verify a pinned archive; returns its local path."""
    os.makedirs(TOOLS, exist_ok=True)
    name = spec["url"].rsplit("/", 1)[1]
    path = os.path.join(TOOLS, name)
    want = expected_sha256(fetch(spec["sums"]).decode(), name)
    if not os.path.exists(path):
        print(f"downloading {spec['url']}")
        data = fetch(spec["url"])
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
    with open(path, "rb") as f:
        got = hashlib.sha256(f.read()).hexdigest()
    if got != want:
        os.remove(path)
        sys.exit(f"{name}: sha256 {got} doesn't match the published {want}")
    return path


def unpack(spec: dict, dest: str):
    """Copy the archive members named in spec["files"] (matched by their path's tail) into dest."""
    with zipfile.ZipFile(tool_archive(spec)) as z:
        for out_name, tail in spec["files"].items():
            member = next((n for n in z.namelist() if n.replace("\\", "/").endswith("/" + tail) or n == tail), None)
            if not member:
                sys.exit(f"{tail} not found in {spec['url']}")
            with z.open(member) as src, open(os.path.join(dest, out_name), "wb") as out:
                shutil.copyfileobj(src, out)


def freeze():
    """PyInstaller one-folder build of native_host.py (one-file would unpack itself on every browser connect)."""
    work = os.path.join(BUILD, "pyinstaller")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--console", "--onedir",
        "--name", HELPER, "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "work"),
        "--specpath", work, "--paths", ROOT,
        # yt-dlp loads extractors and its JS challenge solver files lazily; collect all of it.
        "--collect-all", "yt_dlp", "--hidden-import", "core", "--hidden-import", "updater",
        os.path.join(ROOT, "native_host.py"),
    ], check=True)
    return os.path.join(work, "dist", HELPER)


def stage():
    shutil.rmtree(STAGE, ignore_errors=True)
    shutil.copytree(freeze(), STAGE)
    os.makedirs(os.path.join(STAGE, "bin"))
    unpack(FFMPEG, os.path.join(STAGE, "bin"))
    unpack(DENO, os.path.join(STAGE, "bin"))
    shutil.copytree(os.path.join(ROOT, "extension"), os.path.join(STAGE, "extension"))
    shutil.copy(os.path.join(ROOT, "installer", "setup-guide.html"), STAGE)
    for doc in ("README.md", "CHANGELOG.md"):
        shutil.copy(os.path.join(ROOT, doc), STAGE)
    print(f"staged {STAGE}")


def iscc() -> str:
    candidates = [os.environ.get("ISCC"), shutil.which("ISCC"),
                  os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    sys.exit("Inno Setup 6 not found: install it or set ISCC to the path of ISCC.exe")


def build(tag: str, out: str) -> str:
    version, version_name = manifest_version()
    stage()
    os.makedirs(out, exist_ok=True)
    name = f"YT-Media-Harvester-Setup-{tag}"
    subprocess.run([
        iscc(), f"/DAppVersion={version}", f"/DVersionName={version_name}", f"/DStage={STAGE}",
        f"/DOutDir={os.path.abspath(out)}", f"/DOutputName={name}", os.path.join(ROOT, "installer", "setup.iss"),
    ], check=True)
    return os.path.join(os.path.abspath(out), f"{name}.exe")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("the installer can only be built on Windows")
    if sys.argv[1:2] == ["--stage-only"]:
        stage()
    else:
        tag = sys.argv[1] if len(sys.argv) > 1 else f"v{manifest_version()[0]}"
        print(build(tag, sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dist")))
