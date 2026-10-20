# YT Media Harvester

A Chrome extension that downloads the YouTube videos you have open as **MP3** or **MP4**, with the thumbnail embedded as cover art and the video's metadata (title, channel, date, description, URL) written into the file.

The extension is a small UI. The actual downloading is done by a local Python helper built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), which the extension starts automatically when you need it.

> **Status:** alpha (v0.1.0). Windows and Google Chrome only for now.

## Features

- Lists every open YouTube video tab in the popup, current tab first, with thumbnail and title.
- One click to save as MP3 (192 kbps) or MP4 (best MP4 video + M4A audio).
- Cover art and tags embedded in both formats; chapters added to MP4s.
- Live progress bar per tab: downloading, converting and tagging, done.
- Helper starts by itself through Chrome native messaging and stops after 30 idle minutes.
- Choose the download folder from a settings page (type a path or pick one with **Browse…**).
- Automatic retries with other YouTube player clients, then with your Chrome cookies, when YouTube returns 403.

## Requirements

- Windows 10 or 11
- Google Chrome
- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on `PATH` (conversion, tagging, thumbnail embedding)
- [Node.js](https://nodejs.org/) on `PATH` (yt-dlp uses it to solve YouTube's JavaScript challenge)

## Setup

1. **Install Python 3.10+** from [python.org](https://www.python.org/downloads/) and tick **Add python.exe to PATH**. Install ffmpeg and Node.js too (see Requirements).

2. **Load the extension:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and select the `extension/` folder.

3. **Run `install.bat`** (double-click it), then reload the extension in `chrome://extensions`. It:
   - creates a `.venv` folder inside the repo, unless one already exists there or in the parent folder (the older setup);
   - installs `requirements.txt` into it;
   - registers the native messaging host, so the extension can start the helper itself.

   If anything fails it says what went wrong and ends with "Install did not finish". Run it again after you update the repo or move its folder.

## Usage

1. Open one or more YouTube videos.
2. Click the extension icon. Each open video appears as a card.
3. Click **MP3** or **MP4** on a card. The first click after a reboot takes a few seconds while the helper starts.
4. When the card says **Saved**, click **Open folder** in the popup to see the file.

Clicking a card's thumbnail or title switches to that tab.

### Changing the download folder

Click **Settings** in the popup (or right-click the extension icon and choose **Options**). Type a path or click **Browse…**, then **Save**. **Use default** goes back to the `downloads/` folder inside the repo. The change applies to the next download; downloads already running keep their folder.

The choice is stored in `config.json` next to `server.py`:

```json
{ "out_dir": "D:\\Music" }
```

An empty value means the default folder.

## Scripts

| Script | What it does |
| --- | --- |
| `install.bat` | Registers the native messaging host with Chrome (per user, no admin needed). |
| `uninstall.bat` | Removes that registration. |
| `start.bat` | Runs the helper by hand in a visible console window, without idle shutdown. Useful for debugging. The extension still needs `install.bat` to get the helper's token. |
| `native_host.bat` | Launcher Chrome calls; you don't run it yourself. |

## Troubleshooting

- **"Helper couldn't start"**: run `install.bat`, reload the extension, and check that `install.bat` finished without errors. Details are in `helper.log`.
- **403 / "Sign in to confirm" errors**: the helper already retries with other clients and your Chrome cookies. Updating yt-dlp usually fixes persistent failures: run `install.bat` again or `.venv\Scripts\pip install -U yt-dlp`.
- **"Chrome 127+ on Windows locks them" in an error**: Chrome now encrypts its cookies so other programs can't read them while it runs. Export a `cookies.txt` for youtube.com with a cookies.txt browser extension, then add its path to `config.json`, for example `"cookies_file": "D:\\cookies\\youtube.txt"`. The helper then uses that file for its last retry instead of Chrome's cookies.
- **No cover art or tags**: ffmpeg is missing from `PATH`.
- **Browse… does nothing**: the folder picker can open behind Chrome. Check the taskbar, or type the path instead.
- **Port 8765 in use**: another program is using the helper's port. Close it, or change `PORT` in both `server.py` and `native_host.py` and `API` in the extension's JS files, plus `host_permissions` in `manifest.json`.

## How it works

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the components, the request flow and the helper's HTTP API.

## Disclaimer

Only download content you have the right to download. Respect YouTube's Terms of Service and the rights of creators.
