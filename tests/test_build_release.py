"""The release script packages the right files and refuses mismatched versions."""
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "build_release.py")


def run(tag, out):
    return subprocess.run([sys.executable, SCRIPT, tag, str(out)], cwd=ROOT, capture_output=True, text=True)


def current_tag():
    with open(os.path.join(ROOT, "extension", "manifest.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"## v{version}"):
                return line.split()[1]
    return None


def test_builds_zip_for_current_version(tmp_path):
    tag = current_tag()
    assert tag, "CHANGELOG.md needs a section for the manifest version"
    r = run(tag, tmp_path)
    assert r.returncode == 0, r.stderr
    names = zipfile.ZipFile(tmp_path / f"YT-Media-Harvester-{tag}.zip").namelist()
    top = f"YT-Media-Harvester-{tag}/"
    assert top + "extension/manifest.json" in names and top + "install.bat" in names and top + "core.py" in names
    assert not any(n.startswith((top + "tests/", top + ".github/")) for n in names)
    assert (tmp_path / "SHA256SUMS.txt").read_text().endswith(f"YT-Media-Harvester-{tag}.zip\n")


def test_checksums_cover_the_setup_exe(tmp_path):
    tag = current_tag()
    (tmp_path / f"YT-Media-Harvester-Setup-{tag}.exe").write_bytes(b"setup")
    assert run(tag, tmp_path).returncode == 0
    lines = (tmp_path / "SHA256SUMS.txt").read_text().splitlines()
    assert [line.split()[1] for line in lines] == [f"YT-Media-Harvester-{tag}.zip", f"YT-Media-Harvester-Setup-{tag}.exe"]


def test_rejects_wrong_version_and_bad_tags(tmp_path):
    assert run("v99.0.0", tmp_path).returncode != 0
    assert run("0.2.0", tmp_path).returncode != 0
