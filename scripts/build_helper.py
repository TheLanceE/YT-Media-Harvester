"""Build the standalone helper the Windows installer ships: native_host.exe plus everything it needs.

  python scripts/build_helper.py [out_dir] [--tools]

Writes out_dir (default dist/helper) with native_host.exe and its PyInstaller files, a copy of extension/,
and, with --tools, bin/ffmpeg.exe, bin/ffprobe.exe (BtbN's GPL build) and bin/node.exe, downloaded and checksum-verified.
Run it on Windows with requirements-build.txt installed; the result needs no Python on the user's machine.
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_VERSION = "22.11.0"  # LTS; only node.exe is kept, for yt-dlp's YouTube JS challenge
NODE_ZIP = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ZIP}"
NODE_SUMS = f"https://nodejs.org/dist/v{NODE_VERSION}/SHASUMS256.txt"
FFMPEG_RELEASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"  # GPL builds, with checksums.sha256


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()


def verified(url: str, expected: str) -> bytes:
    data = fetch(url)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected.strip().lower():
        sys.exit(f"checksum mismatch for {url}: got {actual}, expected {expected}")
    return data


def extract(data: bytes, names: list[str], dest: str):
    """Copy the zip members whose file name is in `names` (wherever they sit in the zip) into dest."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        found = {os.path.basename(m): m for m in z.namelist() if os.path.basename(m) in names}
        missing = set(names) - set(found)
        if missing:
            sys.exit(f"not in the archive: {', '.join(sorted(missing))}")
        for name, member in found.items():
            with z.open(member) as src, open(os.path.join(dest, name), "wb") as dst:
                shutil.copyfileobj(src, dst)


def download_tools(bin_dir: str):
    os.makedirs(bin_dir, exist_ok=True)
    sums = dict(reversed(line.split()) for line in fetch(NODE_SUMS).decode().splitlines() if line.strip())
    extract(verified(NODE_URL, sums[NODE_ZIP]), ["node.exe"], bin_dir)
    # The newest stable branch build, e.g. ffmpeg-n8.1-latest-win64-gpl-8.1.zip, rather than master.
    sums = fetch(FFMPEG_RELEASE + "checksums.sha256").decode()
    builds = re.findall(r"^(\w+)\s+(ffmpeg-n([\d.]+)-latest-win64-gpl-[\d.]+\.zip)$", sums, re.M)
    if not builds:
        sys.exit("no stable win64 GPL build listed in the FFmpeg-Builds checksums")
    digest, name, _ = max(builds, key=lambda b: tuple(int(n) for n in b[2].split(".")))
    extract(verified(FFMPEG_RELEASE + name, digest), ["ffmpeg.exe", "ffprobe.exe"], bin_dir)
    print(f"tools in {bin_dir}: {', '.join(sorted(os.listdir(bin_dir)))}")


def build(out: str, tools: bool):
    work = os.path.join(ROOT, "build", "pyinstaller")
    dist = os.path.join(work, "dist")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
        "--name", "native_host", "--distpath", dist, "--workpath", work, "--specpath", work,
        os.path.join(ROOT, "native_host.py"),
    ], check=True)
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(dist, "native_host"), out)
    shutil.copytree(os.path.join(ROOT, "extension"), os.path.join(out, "extension"))
    if tools:
        download_tools(os.path.join(out, "bin"))
    print(f"helper built in {out}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(os.path.abspath(args[0] if args else os.path.join(ROOT, "dist", "helper")), "--tools" in sys.argv)
