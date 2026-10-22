# Architecture

YT Media Harvester has two halves: a Manifest V3 Chrome extension that provides the UI, and a local Python helper that does the downloading with yt-dlp and ffmpeg. They talk over Chrome native messaging: Chrome starts the helper as a child process and exchanges JSON messages with it over stdin/stdout. There is no network port. See [ADR-0001](adr/0001-extension-to-helper-transport.md) for why.

```
┌──────────────────────── Chrome ─────────────────────────┐
│  popup.js / options.js                                  │
│     │ chrome.runtime.sendMessage({cmd, args})           │
│     ▼                       ▲ chrome.storage.session    │
│  background.js (service worker)  ── jobs, badge,        │
│     │ connectNative port          notifications         │
└─────┼───────────────────────────────────────────────────┘
      │ length-prefixed JSON over stdin/stdout
      ▼
┌──────────────────────────────┐
│ native_host.py (via .bat)    │  requests in, replies + job events out
│   core.py: jobs, yt-dlp,     │  yt-dlp/ffmpeg output -> helper.log
│   ffmpeg, node, out_dir      │
└──────────────────────────────┘
```

## Components

| File | Role |
| --- | --- |
| `extension/manifest.json` | MV3 manifest. Permissions: `tabs`, `nativeMessaging`, `storage`, `notifications`, `cookies`, plus host access to `*.youtube.com` (needed to read its cookies). The `key` field pins the extension ID so the native host can allow it. |
| `extension/background.js` | Service worker. Owns the native port, forwards commands from the popup and options page, mirrors job events into `chrome.storage.session`, sets the badge, shows a notification when a download finishes, and lets the helper go a minute after the last job. |
| `extension/helper.js` | `helper(cmd, args)`: what the popup and options page call to reach `background.js`. |
| `extension/popup.js` | Lists open YouTube watch tabs, starts downloads, and draws each card from the stored jobs, so progress survives closing and reopening the popup. |
| `extension/options.js` | Settings page for the download folder. |
| `native_host.py` | The helper process Chrome runs. Reads requests, runs them in threads, streams job events. Also installs and uninstalls its own registration. |
| `core.py` | The download engine: folder config, URL checks, jobs in background threads, the yt-dlp pipeline and retry ladder, partial-file cleanup. |
| `*.bat` | Wrappers that run the Python files with `.venv\Scripts\python.exe` in the repo, falling back to `..\.venv`. `install.bat` creates the venv if neither exists, installs `requirements.txt`, and registers the host. |

## Starting and stopping the helper

1. `install.bat` writes `com.yt_tab_downloader.helper.json` (it names `native_host.bat` and allows only this extension's origin) and points `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.yt_tab_downloader.helper` at it.
2. The first command from the popup or options page makes `background.js` call `chrome.runtime.connectNative`. Chrome starts `native_host.bat` and keeps it running while the port is open. An open native port also keeps the service worker alive.
3. `native_host.py` keeps the real stdout for messages only: before anything else runs it moves file descriptors 1 and 2 to `helper.log`, so yt-dlp, ffmpeg and `print()` can't corrupt the stream.
4. A minute after the last job finishes, `background.js` disconnects. The host sees stdin close and exits. If Chrome quits mid-download, the host deletes that job's partial files (`.part`, unmerged streams, the cover image, a half-converted output) before exiting.

## Download flow

1. The popup sends `{cmd: "download", args: {url, format}}`. `background.js` forwards it to the host.
2. The host checks that it's a YouTube video URL and that the format is `mp3` or `mp4`, creates a job, starts a thread, and replies `{job}`.
3. Every 0.5 s the host sends a `job` event for any job whose state changed. `background.js` stores it under `jobs` in `chrome.storage.session` and updates the badge; the popup redraws from storage.
4. The job runs yt-dlp with:
   - **MP3**: `bestaudio`, extracted to MP3 at 192 kbps.
   - **MP4**: best MP4 video + M4A audio, merged to MP4, with chapters.
   - Both: thumbnail downloaded and converted to JPG, metadata written with `FFmpegMetadata`, cover embedded with `EmbedThumbnail`. Files are named `%(title)s [%(id)s].%(ext)s`, so two videos with the same title don't overwrite each other.
   - Node is passed to yt-dlp as its JavaScript runtime when found on `PATH`.
5. On a 403 or "page needs to be reloaded" error, the job retries in order: plain retry, `tv`/`web_safari` player clients, `android_vr`/`mweb` clients, then cookies. YouTube's "Sign in to confirm you're not a bot" check skips straight to the cookie rung, since other clients get the same answer. Cookies come from, in order: the `cookies_file` in `config.json`; the browser's youtube.com cookies, which the service worker reads with `chrome.cookies` and sends with each `download` request (the helper writes them to a private temp cookies.txt and deletes it when the job ends); Chrome's cookie store. Any other error stops immediately. The first error message is reported, with a hint for the bot check or an unreadable Chrome cookie store.

Jobs live in the host's memory and in `chrome.storage.session`. Finished jobs stay listed for an hour; closing Chrome clears them.

## Message protocol

Each message is UTF-8 JSON preceded by its length as a 32-bit integer in native byte order (Chrome's native messaging format).

| Request `{id, cmd, ...}` | Reply `{id, ok: true, ...}` |
| --- | --- |
| `hello` | `{version, out_dir, default_out_dir}` |
| `config` with optional `out_dir` (empty resets) | `{out_dir, default_out_dir}` |
| `choose_folder` | Shows the folder picker (tkinter). `{out_dir}` or `{cancelled: true, out_dir}` |
| `open` | Opens the download folder in the file manager. `{}` |
| `download` with `url`, `format` | `{job}` |
| `jobs` | `{jobs: {id: job}}` |

A failed request gets `{id, ok: false, error}`. Job events are `{event: "job", job, status, progress, part?, url, format, out_dir, started, title?, error?}`, where `status` is `running`, `done` or `error` and `progress` is a percentage string or `"converting"`.

## Security notes

- Nothing listens on the network. Only Chrome can start the host, and the host manifest allows only the pinned extension ID.
- Web pages can't talk to the host or to `background.js`: the worker only accepts messages from the extension's own pages.
- Download URLs are parsed and must be a video on `youtube.com`, `www.`/`m.`/`music.youtube.com` or `youtu.be`.
- Job IDs are random (`uuid4`).
- YouTube cookies only travel from the browser to the local helper over native messaging. The helper keeps only youtube.com cookies, writes them to a temp file readable by the current user only, and deletes it when the job ends. If Chrome quits mid-download, that file can be left in the temp folder.

## Local files

These are created at runtime and are ignored by git: `config.json` (download folder, optional `cookies_file`), `helper.log` (helper output, started over when it passes 1 MB), `com.yt_tab_downloader.helper.json` (native host manifest, written by `install.bat`), `.venv/`, and `downloads/` (default output folder).

## Standalone build

`scripts/build_helper.py` freezes `native_host.py` and `core.py` with PyInstaller into `native_host.exe`, copies `extension/` next to it and, with `--tools`, adds `bin/ffmpeg.exe`, `bin/ffprobe.exe` and `bin/node.exe`. In that build `BASE` is the folder holding `native_host.exe`, so `config.json`, `helper.log` and `downloads/` live there. The host manifest points straight at the `.exe`. The v0.4 installer (#5) ships this folder.

A frozen build can't pip-upgrade yt-dlp, and old yt-dlp releases stop working as YouTube changes. `updater.py` checks PyPI at most once a day (in a background thread at helper start, or on demand through `update_ytdlp` from Settings), verifies the wheel's sha256 and unpacks `yt_dlp/` into `lib/` next to the helper. At the next start `updater.activate()` puts `lib/` first on `sys.path`, before anything imports yt-dlp, so it wins over the frozen copy. If it fails to import, `lib/` is deleted and that version is recorded in `updater.json` as skipped.

## Platform limits

The helper is Windows-only today: registration uses the Windows registry (`winreg`), and the `.bat` wrappers are Windows batch files. `install.bat` writes the host key for Chrome, Edge and Brave. Firefox would need a second host manifest using `allowed_extensions` (ADR-0001 follow-up).
