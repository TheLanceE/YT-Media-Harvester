# Architecture

YT Media Harvester has two halves: a Manifest V3 Chrome extension that provides the UI, and a local Python helper that does the downloading with yt-dlp and ffmpeg. They talk over HTTP on `127.0.0.1:8765`. A Chrome native messaging host bridges the gap when the helper isn't running yet.

```
┌──────────────── Chrome ────────────────┐
│  popup.html / popup.js                 │
│  options.html / options.js             │
└──────┬───────────────────────┬─────────┘
       │ 1. sendNativeMessage  │ 2. HTTP (fetch)
       │    {cmd: "start"}     │    127.0.0.1:8765
       ▼                       ▼
┌──────────────────┐   ┌──────────────────────────┐
│ native_host.py   │──▶│ server.py                │
│ (via .bat, stdio)│   │ ThreadingHTTPServer      │
│ starts server if │   │ yt-dlp + ffmpeg + node   │
│ port is closed   │   │ writes to out_dir        │
└──────────────────┘   └──────────────────────────┘
```

## Components

| File | Role |
| --- | --- |
| `extension/manifest.json` | MV3 manifest. Permissions: `tabs`, `nativeMessaging`, and host access to `http://127.0.0.1:8765/*`. The `key` field pins the extension ID so the native host can allow it. |
| `extension/popup.js` | Lists open YouTube watch tabs, starts downloads, polls job status, shows the helper state and save folder. |
| `extension/options.js` | Settings page for the download folder. |
| `server.py` | The helper. HTTP API, download jobs in background threads, folder config, idle shutdown. |
| `native_host.py` | Native messaging host. Also installs and uninstalls its own registration. |
| `*.bat` | Wrappers that run the Python files with `..\.venv\Scripts\python.exe`. |

## Starting the helper

1. Every HTTP call goes through `extension/helper.js`. If it has no token in `chrome.storage.session`, gets a `401`, or can't reach the server, it calls `chrome.runtime.sendNativeMessage("com.yt_tab_downloader.helper", {cmd: "start"})`.
2. Chrome looks up the host in `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.yt_tab_downloader.helper`, which points to `com.yt_tab_downloader.helper.json`. That manifest names `native_host.bat` and only allows this extension's origin.
3. `native_host.py` checks whether port 8765 is open. If not, it launches `server.py --idle-minutes 30` hidden (`CREATE_NO_WINDOW`) and detached from Chrome's job object so it outlives the host, with output going to `helper.log`. It waits up to 15 seconds for the port to open, then replies `{ok: true, token}`. The token is created in `config.json` on first use.
4. The extension stores the token and retries its HTTP call once.

The server exits on its own once 30 minutes pass with no requests and no running job.

## Download flow

1. The popup `POST`s `/download` with `{url, format}`. The server checks that it's a YouTube watch or `youtu.be` URL and that the format is `mp3` or `mp4`, creates a job, and starts a thread. It replies `202 {job}`.
2. The popup polls `GET /status/<job>` every 700 ms and updates the card's progress bar.
3. The job runs yt-dlp with:
   - **MP3**: `bestaudio`, extracted to MP3 at 192 kbps.
   - **MP4**: best MP4 video + M4A audio, merged to MP4, with chapters.
   - Both: thumbnail downloaded and converted to JPG, metadata written with `FFmpegMetadata`, cover embedded with `EmbedThumbnail`. Files are named `%(title)s [%(id)s].%(ext)s`, so two videos with the same title don't overwrite each other.
   - Node is passed to yt-dlp as its JavaScript runtime when found on `PATH`.
4. On a 403 or "page needs to be reloaded" error, the job retries in order: plain retry, `tv`/`web_safari` player clients, `android_vr`/`mweb` clients, then cookies (the `cookies_file` from `config.json` if set, otherwise Chrome's cookie store). Any other error stops immediately. The first error message is reported; if reading Chrome's cookies failed, a hint about Chrome 127+ cookie encryption and `cookies_file` is added.

Jobs live in memory only. Restarting the helper forgets them.

## HTTP API

All responses are JSON. Base URL `http://127.0.0.1:8765`. Every request needs an `X-Helper-Token` header and is otherwise rejected with `401`.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| GET | `/` | | `{ok, out_dir, default_out_dir}` |
| GET | `/open` | | Opens the download folder in Explorer, then same as `/`. |
| POST | `/download` | `{url, format: "mp3" \| "mp4"}` | `202 {job}`, or `400 {error}` |
| GET | `/status/<job>` | | `{status: "running" \| "done" \| "error", progress, out_dir, title?, error?}`. `progress` is a percentage string or `"converting"`; `part` is 2 while an MP4's audio stream downloads. Finished jobs are dropped after 10 minutes. |
| POST | `/config` | `{out_dir}` (empty resets) | `{ok, out_dir}`, or `400 {error}` |
| POST | `/choose-folder` | `{}` | Shows the Windows folder picker (tkinter). `{ok, out_dir}` or `{ok: false, cancelled: true}` |

## Security notes

- The server binds to `127.0.0.1` only, so nothing outside the machine can reach it.
- Every route requires the `X-Helper-Token` header, and a request whose `Origin` is set to anything other than this extension's `chrome-extension://` origin is rejected. A web page can't send a custom header without a CORS preflight, and preflights are refused for every origin except the extension's, so pages can't start downloads, open the folder, or read the folder path.
- Requests must arrive with `Host: 127.0.0.1:8765` (or `localhost:8765`), which blocks DNS-rebinding pages. Download URLs are parsed and must be a video on `youtube.com`, `www.`/`m.`/`music.youtube.com` or `youtu.be`. Malformed or oversized (over 64 KB) bodies get a `400`.
- The token lives in `config.json` and reaches the extension only through the native messaging host. Any local program that can read your files can still read it; the helper only defends against web pages.
- Job IDs are random (`uuid4`).
- The native messaging host only accepts the pinned extension ID.

## Local files

These are created at runtime and are ignored by git: `config.json` (download folder and token), `helper.log` (helper output, started over when it passes 1 MB), `com.yt_tab_downloader.helper.json` (native host manifest, written by `install.bat`), and `downloads/` (default output folder).

## Platform limits

The helper is Windows-only today: registration uses the Windows registry (`winreg`), `/open` uses `os.startfile`, and the `.bat` wrappers assume the `..\.venv` layout. Only Chrome's registry key is written, so other Chromium browsers (Edge, Brave) need their own registration.
