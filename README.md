# YT Media Harvester

A Chrome extension that downloads the YouTube videos you have open as **MP3** or **MP4**, with the thumbnail embedded as cover art and the video's metadata (title, channel, date, description, URL) written into the file.

The extension is a small UI. The actual downloading is done by a local Python helper built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), which the extension starts automatically when you need it.

> **Status:** beta (v0.3.0). Windows and Google Chrome only for now.

## Features

- Lists every open YouTube video tab in the popup, current tab first, with thumbnail and title.
- One click to save as MP3 (192 kbps) or MP4 (best MP4 video + M4A audio).
- Cover art and tags embedded in both formats; chapters added to MP4s.
- Live progress bar per tab: downloading, converting and tagging, done.
- Helper starts by itself through Chrome native messaging and stops after 30 idle minutes.
- Choose the download folder from a settings page (type a path or pick one with **Browse…**).
- Automatic retries with other YouTube player clients, then with your browser's YouTube cookies, when YouTube returns 403 or asks you to sign in.
- Works in Chrome, Edge and Brave.

## Requirements

- Windows 10 or 11
- Google Chrome
- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on `PATH` (conversion, tagging, thumbnail embedding)
- [Node.js](https://nodejs.org/) on `PATH` (yt-dlp uses it to solve YouTube's JavaScript challenge)

## Setup

Get the code: download the latest `YT-Media-Harvester-vX.Y.Z.zip` from [Releases](https://github.com/TheLanceE/YT-Media-Harvester/releases) and unzip it, or clone the repo.

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
3. Click **MP3** or **MP4** on a card. The first click takes a few seconds while the helper starts.
4. You can close the popup: the download keeps going, the extension icon shows how many are running, and a notification says when each one is saved. Reopen the popup to see progress.
5. When the card says **Saved**, click **Open folder** in the popup to see the file.

Clicking a card's thumbnail or title switches to that tab.

### Changing the download folder

Click **Settings** in the popup (or right-click the extension icon and choose **Options**). Type a path or click **Browse…**, then **Save**. **Use default** goes back to the `downloads/` folder inside the repo. The change applies to the next download; downloads already running keep their folder.

The choice is stored in `config.json` next to `core.py`:

```json
{ "out_dir": "D:\\Music" }
```

An empty value means the default folder.

## Scripts

| Script | What it does |
| --- | --- |
| `install.bat` | Registers the native messaging host with Chrome (per user, no admin needed). |
| `uninstall.bat` | Removes that registration. |
| `native_host.bat` | The helper itself. Chrome starts it when the extension needs it and stops it about a minute after the last download; you don't run it yourself. |

## Troubleshooting

- **"Helper couldn't start"**: run `install.bat`, reload the extension, and check that `install.bat` finished without errors. Details are in `helper.log`.
- **403 / "Sign in to confirm you're not a bot" errors**: the helper already retries with other clients and then with your browser's YouTube cookies, so being signed in to YouTube in the browser usually gets past it. Otherwise the bot check clears after an hour or so. Updating yt-dlp usually fixes persistent failures: run `install.bat` again or `.venv\Scripts\pip install -U yt-dlp`.
- **Using your own cookies.txt**: to override the browser's cookies, export a `cookies.txt` for youtube.com and add its path to `config.json`, for example `"cookies_file": "D:\\cookies\\youtube.txt"`. The helper then uses that file for its last retry.
- **No cover art or tags**: ffmpeg is missing from `PATH`.
- **Browse… does nothing**: the folder picker can open behind Chrome. Check the taskbar, or type the path instead.
- **Downloads stop when Chrome closes**: the helper runs inside Chrome's native messaging connection, so quitting Chrome stops running downloads and deletes their partial files. Start them again after reopening Chrome.

## Making a release

1. Bump `version` (and `version_name` for pre-releases) in `extension/manifest.json`, and turn `## Unreleased` in `CHANGELOG.md` into `## vX.Y.Z[-label] (date)`. Merge that PR.
2. In **Actions → Release → Run workflow**, enter the tag (e.g. `v0.3.0-alpha`). It runs the tests, checks the manifest and changelog match the tag, builds the zip and `SHA256SUMS.txt`, creates the tag and publishes the release. Tags with a `-label` are marked pre-release.

## How it works

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the components, the request flow and the helper's HTTP API.

## Disclaimer

Only download content you have the right to download. Respect YouTube's Terms of Service and the rights of creators.
