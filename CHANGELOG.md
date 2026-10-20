# Changelog

Versions follow the git tags. `extension/manifest.json` carries the same number in `version`, with the pre-release label in `version_name`.

## Unreleased

- The download engine moved from `server.py` into `core.py`, ready for the native-messaging transport (#11). "Open folder" also works on macOS and Linux.
- Release workflow: Actions → Release builds the zip, SHA256SUMS and notes from this file and publishes the GitHub Release.

## v0.2.0-alpha (2026-10-20)

Security and setup hardening. Tested on Windows 11 with Chrome: fresh install and downloads.

### Security
- The helper only answers this extension: exact origin, a token from the native host on every request, and no wildcard CORS (#1).
- Download URLs must be a video on youtube.com, www/m/music.youtube.com or youtu.be (#7).
- Requests must be addressed to `127.0.0.1:8765` or `localhost:8765`, which blocks DNS rebinding (#7).
- Job IDs are random (#1); malformed or oversized request bodies get a 400 (#7).

### Fixed
- `install.bat` creates its own `.venv`, installs `requirements.txt`, and reports failures instead of printing "Done" (#9).
- Same-titled videos no longer overwrite each other: files are named `Title [videoID].ext` (#7).
- Progress is computed from byte counts; MP4s say whether video or audio is downloading (#7).
- When Chrome's cookies can't be read (Chrome 127+), the error says why; `cookies_file` in `config.json` can point to a cookies.txt (#8).
- Finished jobs are dropped after 10 minutes; `helper.log` starts over past 1 MB (#7).

### Project
- CI on every PR: ruff, unit tests on Linux and Windows, extension syntax checks, and a clean-machine `install.bat` run (#2, #7, #9).
- `requirements.txt` pins yt-dlp 2025.11.12 or newer (#7).
- ADR-0001 records the plan to move from the local HTTP server to native messaging (#1).

## v0.1.0-alpha

First pre-release: Chrome extension plus local yt-dlp helper, MP3/MP4 with cover art and tags.
