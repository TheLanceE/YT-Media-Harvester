"""Chrome native messaging host: starts server.py in the background when the extension asks.

  python native_host.py install     register with Chrome (run once, via install.bat)
  python native_host.py uninstall   remove the registration
Chrome itself runs it through native_host.bat; it then reads one message and replies.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import time

NAME = "com.yt_tab_downloader.helper"
EXTENSION_ID = "kcnffalmlnicdbnolfbgonjbjaekcleg"  # pinned by "key" in extension/manifest.json
HOST, PORT = "127.0.0.1", 8765
IDLE_MINUTES = 30  # the server stops itself after this long with no requests and no running job
BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, f"{NAME}.json")
REG_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{NAME}"


def server_up() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5):
            return True
    except OSError:
        return False


def start_server() -> dict:
    if server_up():
        return {"ok": True, "started": False}
    log = open(os.path.join(BASE, "helper.log"), "ab")
    cmd = [sys.executable, os.path.join(BASE, "server.py"), "--idle-minutes", str(IDLE_MINUTES)]
    kw = {"cwd": BASE, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
    if os.name == "nt":
        # Hidden console (so ffmpeg/node children don't flash windows), and outside Chrome's job
        # object so the server keeps running after this host exits.
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:  # job doesn't allow breakaway
            subprocess.Popen(cmd, creationflags=flags, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)
    for _ in range(60):  # importing yt_dlp takes a few seconds
        time.sleep(0.25)
        if server_up():
            return {"ok": True, "started": True}
    return {"ok": False, "error": "helper did not start, see helper.log"}


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    return json.loads(sys.stdin.buffer.read(struct.unpack("<I", raw)[0]))


def send_message(msg: dict):
    data = json.dumps(msg).encode()
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def install():
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({
            "name": NAME,
            "description": "YT Tab Downloader helper launcher",
            "path": os.path.join(BASE, "native_host.bat"),
            "type": "stdio",
            "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
        }, f, indent=2)
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValue(k, "", winreg.REG_SZ, MANIFEST)
    print(f"Registered {NAME} -> {MANIFEST}")


def uninstall():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        pass
    if os.path.exists(MANIFEST):
        os.remove(MANIFEST)
    print(f"Removed {NAME}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["install"]:
        install()
    elif sys.argv[1:2] == ["uninstall"]:
        uninstall()
    else:  # launched by Chrome
        if os.name == "nt":
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        msg = read_message()
        if msg is not None:
            send_message(start_server() if msg.get("cmd") == "start" else {"ok": False, "error": "unknown cmd"})
