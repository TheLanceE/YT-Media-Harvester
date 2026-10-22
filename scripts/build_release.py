"""Build a release: check the version, write the zip, its SHA256SUMS and the release notes.

  python scripts/build_release.py v0.2.0-alpha [out_dir]

RELEASE_ROOT points it at another checkout (the release workflow uses this to package an older commit).

The zip holds what a user needs to run the app (extension/, the helper and the .bat files),
under one top-level folder. Notes are the tag's section of CHANGELOG.md.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.environ.get("RELEASE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)(?:-([0-9A-Za-z.]+))?$")
LEAVE_OUT = ("tests/", "scripts/", "docs/", ".github/", ".gitattributes", ".gitignore", "ruff.toml", "requirements-dev.txt")


def fail(msg: str):
    sys.exit(f"release check failed: {msg}")


def check_version(tag: str) -> str:
    m = TAG_RE.match(tag)
    if not m:
        fail(f"{tag!r} is not vMAJOR.MINOR.PATCH with an optional -label")
    with open(os.path.join(ROOT, "extension", "manifest.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]
    if version != m.group(1):
        fail(f"extension/manifest.json version is {version}, tag says {m.group(1)}")
    return m.group(1)


def changelog_section(tag: str) -> str:
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^## {re.escape(tag)}\b.*?$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        fail(f"CHANGELOG.md has no '## {tag}' section")
    return m.group(1).strip()


def release_files() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return sorted(p for p in tracked if not p.startswith(LEAVE_OUT))


def build(tag: str, out: str) -> list[str]:
    check_version(tag)
    notes = changelog_section(tag)
    os.makedirs(out, exist_ok=True)
    name = f"YT-Media-Harvester-{tag}"
    zip_path = os.path.join(out, f"{name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in release_files():
            z.write(os.path.join(ROOT, rel), f"{name}/{rel}")
    with open(zip_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(out, "SHA256SUMS.txt"), "w", encoding="utf-8") as f:
        f.write(f"{digest}  {name}.zip\n")
    with open(os.path.join(out, "notes.md"), "w", encoding="utf-8") as f:
        f.write(notes + f"\n\n## Install\n\n**Windows installer:** run `YT-Media-Harvester-Setup-{tag}.exe`, tick your browsers, "
                "then follow the one-minute guide it opens to add the extension (Developer mode, Load unpacked). "
                f"No Python needed.\n\n**From source:** unzip `{name}.zip`, load its `extension/` folder in "
                "`chrome://extensions` (Developer mode, Load unpacked), then run `install.bat` and reload the extension. "
                "See README.md.\n")
    return [zip_path, os.path.join(out, "SHA256SUMS.txt")]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for path in build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dist")):
        print(path)
