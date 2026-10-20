# YT-Media-Harvester
Allows users to download MP3s and MP4s from YT alongside thumbnails and provided metadata.

## Usage
Needs the repo `.venv` one folder up with yt-dlp, plus ffmpeg and node on PATH.

1. Chrome -> `chrome://extensions` -> Developer mode -> Load unpacked -> select `extension/`
2. Double-click `install.bat` once. It registers a small launcher with Chrome, so the extension starts the helper by itself. (If you move this folder, run it again.)
3. Click the extension icon on any open YouTube tab: pick MP3 or MP4. The first click after a reboot takes a few seconds while the helper starts.

The helper runs hidden in the background and stops itself after 30 minutes with nothing to do. Its output goes to `helper.log`. `uninstall.bat` removes the launcher. `start.bat` still works if you want to run the helper by hand in a window.

**Download folder:** click **Settings** in the popup (or right-click the extension icon -> Options). Type a path or click **Browse…** to pick one; it applies to the next download, no restart needed. The choice is saved in `config.json` next to `server.py` (`{"out_dir": "D:\\Music"}`); an empty value means the default `downloads/` folder.

## Setting up from a fresh clone
The `.bat` files expect a Python virtual environment named `.venv` in the folder that contains this one. From that parent folder:

```
python -m venv .venv
.venv\Scripts\pip install yt-dlp
```

ffmpeg and node must also be on PATH.
