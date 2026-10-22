"""The installer build script's checksum handling; the build itself runs in CI on Windows."""
import os
import runpy

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
build = runpy.run_path(os.path.join(ROOT, "scripts", "build_installer.py"))
DIGEST = "af669f9a1dcb95fd028c074d0cdc25778daf6aedca92c958d743501d84af5bfb"


def test_reads_sha256sum_listing():
    sums = f"{'1' * 64}  ffmpeg-other.zip\n{DIGEST}  ffmpeg-n8.1-latest-win64-lgpl-8.1.zip\n"
    assert build["expected_sha256"](sums, "ffmpeg-n8.1-latest-win64-lgpl-8.1.zip") == DIGEST


def test_reads_get_filehash_output():
    # Deno's .sha256sum files are PowerShell's Get-FileHash output.
    sums = f"\r\nAlgorithm : SHA256\r\nHash      : {DIGEST.upper()}\r\nPath      : C:\\a\\deno.zip\r\n\r\n"
    assert build["expected_sha256"](sums, "deno-x86_64-pc-windows-msvc.zip") == DIGEST


def test_missing_checksum_stops_the_build():
    with pytest.raises(SystemExit):
        build["expected_sha256"](f"{'1' * 64}  a.zip\n{'2' * 64}  b.zip\n", "c.zip")
