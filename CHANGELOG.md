# Changelog

Versions follow the git tags. `extension/manifest.json` carries the same number in `version`, with the pre-release label in `version_name`.

## Unreleased

Groundwork for the v0.4 one-click installer (#5).

- `scripts/build_helper.py` builds a standalone `native_host.exe` with PyInstaller, so the installed helper needs no Python. With `--tools` it also fetches checksum-verified `ffmpeg.exe`, `ffprobe.exe` (BtbN GPL build) and `node.exe` into `bin/`.
- The helper uses `bin/ffmpeg.exe` and `bin/node.exe` when they're present, and falls back to `PATH` otherwise.
- `native_host install` takes the browsers to register, e.g. `install chrome edge` (no argument means all three). When frozen, the host manifest points at `native_host.exe` instead of `native_host.bat`.
- Windows CI builds the standalone helper and smoke-tests it.

## v0.3.0-beta (2026-10-22)

First beta. The extension now talks to the helper over Chrome native messaging instead of a local web server (ADR-0001).

- Downloads keep running when the popup is closed. Reopening it shows their progress; the icon badge counts running downloads and a notification says when each is saved.
- No local port or token any more: the HTTP server (`server.py`, `auth.py`, `start.bat`) is gone, and only Chrome can start the helper.
- YouTube's "Sign in to confirm you're not a bot" check now goes straight to the cookie retry instead of failing at once, and the error says how to get past it.
- The cookie retry uses the browser's own youtube.com cookies, which the extension reads and passes to the helper (new `cookies` permission, youtube.com only). No more cookies.txt export, and it works around Chrome 127+ cookie encryption and Edge's locked cookie file. A `cookies_file` in config.json still takes precedence.
- install.bat registers the helper for Edge and Brave as well as Chrome.
- The cookie retry gets one more try on YouTube's transient "page needs to be reloaded" error, and when the cookies got past the bot check, the popup shows what stopped them instead of the bot-check message.
- Quitting Chrome mid-download deletes that download's partial files.
- yt-dlp and ffmpeg output can never reach the extension's message stream; it goes to `helper.log`.
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
