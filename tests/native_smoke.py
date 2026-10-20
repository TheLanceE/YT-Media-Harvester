"""End-to-end check on Windows: after install.bat, Chrome's launcher starts the helper and hands back a token.

Speaks the native-messaging framing to native_host.bat the way Chrome does. Run from the repo root.
"""
import json
import os
import struct
import subprocess
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

msg = json.dumps({"cmd": "start"}).encode()
out = subprocess.run(
    ["cmd", "/c", os.path.join(BASE, "native_host.bat")],
    input=struct.pack("<I", len(msg)) + msg, capture_output=True, timeout=120, check=True,
).stdout
length = struct.unpack("<I", out[:4])[0]
reply = json.loads(out[4:4 + length])
print("native host replied:", {k: v for k, v in reply.items() if k != "token"})
assert reply.get("ok") and reply.get("token"), reply

req = urllib.request.Request("http://127.0.0.1:8765/", headers={"X-Helper-Token": reply["token"]})
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.load(r)
print("helper status:", r.status)
assert body["ok"], body
sys.exit(0)
