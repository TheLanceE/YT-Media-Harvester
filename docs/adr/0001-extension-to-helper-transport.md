# ADR-0001: How the extension talks to the download helper

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Lance (maintainer)

## Context

YT Media Harvester is a Manifest V3 Chrome extension plus a local Python helper that runs yt-dlp and ffmpeg (see [ARCHITECTURE.md](../ARCHITECTURE.md)). Downloading stays on the user's machine because only yt-dlp keeps up with YouTube's signature, `n`-parameter and PO token changes. Moving extraction and conversion into the browser (ffmpeg.wasm) was considered and rejected: it would mean maintaining our own extractor, a ~30 MB wasm core, memory-bound conversion of long videos, and separate offscreen/event-page code for Chrome and Firefox.

What is still open is the **transport** between the extension and the helper. Today it is a hybrid:

- A native messaging host (`native_host.py`) is used only as a launcher. It starts `server.py` if port 8765 is closed, then exits.
- All real work goes over HTTP to `http://127.0.0.1:8765`, and the popup polls `/status/<job>` every 700 ms.

Forces at play:

1. **Security.** The server sends `Access-Control-Allow-Origin: *` and checks `Origin` only on `/config` and `/choose-folder`. Any web page the user visits can:
   - `POST /download` as a CORS "simple request" (the body is parsed as JSON whatever the `Content-Type`), filling the download folder.
   - `GET /open`, which pops an Explorer window, with no origin check at all.
   - Read `GET /` and `GET /status/<id>`, which return the download folder path (it usually contains the Windows user name). Job IDs are sequential (`len(jobs)+1`), so they are easy to enumerate.
2. **UX.** Progress lives only in the popup. Closing it stops polling, and there is no history, because jobs are in memory and the extension has no background script.
3. **Install cost already paid.** The pinned extension ID (`key`), the host manifest and the registry key exist and work. That was the expensive part of moving to native messaging.
4. **Reach.** Windows and Chrome only today. Firefox and Edge/Brave would each need their own host registration in either design.
5. **Distribution.** The Chrome Web Store rejects YouTube downloaders, so this stays a load-unpacked or self-hosted extension. There is no store review to satisfy, but also no auto-update channel for the helper.

## Decision

**Move the work itself onto the native messaging channel and retire the HTTP server.** A background service worker holds one `chrome.runtime.connectNative()` port. The host runs jobs in threads and streams progress messages back over stdout. The popup and options page talk to the service worker, not to the helper.

Until that lands, **harden the HTTP helper now** (Option A below). Those fixes are small and close the hole that exists today.

## Options considered

### Option A: Keep the hybrid, lock down HTTP

Require the exact `chrome-extension://kcnffalmlnicdbnolfbgonjbjaekcleg` origin on every endpoint, including `GET`s, and drop the wildcard CORS header. Add a random token, generated into `config.json` and handed to the extension in the native `start` reply, as a required header. (Done; see the Action items.) Use `uuid4()` job IDs.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low. About 30 lines in `server.py` and `popup.js`. |
| Cost | Hours |
| Scalability | Fine for one user. Port conflicts are possible but rare. |
| Team familiarity | High. It is the current code. |

**Pros:** smallest change. The helper is detached, so it survives the browser closing mid-download. It is easy to debug with `curl`.
**Cons:** an open port stays an attack surface that needs every new endpoint to remember the check. Status still dies with the popup. There are two processes and two protocols to maintain (native launcher plus HTTP).

### Option B: Full native messaging transport (chosen)

`host.py` reads length-prefixed JSON commands (`download`, `config`, `choose-folder`, `open`) and writes `progress`, `done` and `error` events. The service worker keeps the port open while jobs run, which also keeps the MV3 worker alive, and mirrors job state into `chrome.storage.session` so the popup can show it when reopened.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium. New service worker, message protocol, host job loop. |
| Cost | A few days |
| Scalability | Fine for one user. One host process per browser profile. |
| Team familiarity | Medium. The registration and framing code already exist in `native_host.py`. |

**Pros:** no port, so nothing for web pages to reach. Chrome enforces `allowed_origins`. Progress and history survive the popup closing. One process and one protocol. The same host works for Firefox with a second manifest using `allowed_extensions`.
**Cons:** if the browser quits, Chrome kills the host and running downloads stop, so the host must clean up partial files. stdout is the message channel, so yt-dlp and ffmpeg output must never reach it (keep `quiet`, log to `helper.log`). Messages are capped at 1 MB, which only matters if we ever send more than status. It is harder to poke at by hand than HTTP.

### Option C: In-browser ffmpeg.wasm

Rejected (see Context). It is listed only so the record is complete.

| Dimension | Assessment |
|-----------|------------|
| Complexity | High. Own extractor plus offscreen document. |
| Cost | Weeks, then ongoing breakage |
| Scalability | Poor. Memory-bound on long videos. |
| Team familiarity | Low |

**Pros:** no local install.
**Cons:** breaks every time YouTube changes, it is slow, and Chrome and Firefox need two code paths.

## Trade-off analysis

A and B use the same yt-dlp/ffmpeg core, so download quality is identical. The choice is between **survives the browser closing** (A) and **no attack surface, plus progress that survives the popup** (B).

For a personal tool, the browser-closing case is rare and recoverable: the user clicks the button again. A page silently triggering downloads, or reading the user's folder path, happens without the user ever knowing. B fixes the popup problem without extra work, while A would need a background poller added on top. And because the launcher already made us pay B's install cost, the remaining work is mostly moving code, not new infrastructure.

A is still worth doing first. It is a few hours of work, closes the hole today, and `server.py` would need refactoring into a reusable core module for B anyway.

## Consequences

- **Easier:** adding Firefox (a second host manifest plus a gecko ID), background downloads with a badge or notifications, a download history in the popup, and new commands without new security checks.
- **Harder:** manual testing without the extension, which needs a small test harness that speaks the framing. Long downloads are tied to the browser's lifetime.
- **Revisit:** packaging the host as a single PyInstaller exe for people without a venv (then call a separate `yt-dlp.exe` so `-U` still works). Also revisit if a non-browser client (CLI, mobile share target) ever needs the helper, since that would bring back the case for a local HTTP API with token auth.

## Action items

1. [x] Harden `server.py`: exact extension origin on all routes, no wildcard CORS, token header, `uuid4()` job IDs.
2. [ ] Split `server.py` into `core.py` (`ydl_opts`, `run_job`, config) and transports.
3. [ ] Add the host job loop and message protocol. Route all yt-dlp and ffmpeg output away from stdout.
4. [ ] Add a background service worker that owns `connectNative` and stores jobs in `chrome.storage.session`. Point the popup and options page at it.
5. [ ] Delete partial files when the host's stdin closes mid-job.
6. [ ] Remove `server.py`, the port check and the `host_permissions` entry. Update ARCHITECTURE.md.
7. [ ] Follow-up: Firefox host manifest and `browser_specific_settings.gecko.id`. Make `/open` cross-platform.
