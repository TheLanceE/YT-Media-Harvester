"""End-to-end check on Windows: after install.bat, the registered native host answers the way Chrome expects.

Talks to native_host.bat with Chrome's framing. Run from the repo root, or pass a built native_host.exe to test that.
"""
import json
import os
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

msg = json.dumps({"id": 1, "cmd": "hello"}).encode()
ORIGIN = "chrome-extension://smoke-test/"
if len(sys.argv) > 1:  # a built native_host.exe (scripts/build_helper.py): Chrome starts an .exe directly
    p = subprocess.Popen([sys.argv[1], ORIGIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
else:
    # Start the host the way Chrome does, so a folder path with spaces or "&" works here too.
    bat = os.path.join(BASE, "native_host.bat")
    p = subprocess.Popen(f'cmd /d /s /c ""{bat}" {ORIGIN}"', stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(struct.pack("=I", len(msg)) + msg)
p.stdin.flush()
length = struct.unpack("=I", p.stdout.read(4))[0]
reply = json.loads(p.stdout.read(length))
p.stdin.close()
print("native host replied:", reply)
assert reply.get("id") == 1 and reply.get("ok") and reply.get("version"), reply
assert p.wait(timeout=60) == 0, "host did not exit when stdin closed"
