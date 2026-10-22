"""End-to-end check on Windows: the native host answers the way Chrome expects.

  python tests/native_smoke.py [host]     host defaults to native_host.bat; pass the installed or frozen
                                          YTMediaHarvesterHelper.exe to check that build instead

Talks to the host with Chrome's framing. Run from the repo root.
"""
import json
import os
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

host = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "native_host.bat")
msg = json.dumps({"id": 1, "cmd": "hello"}).encode()
# Start the host the way Chrome does, so a folder path with spaces or "&" works here too.
p = subprocess.Popen(f'cmd /d /s /c ""{host}" chrome-extension://smoke-test/"', stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(struct.pack("=I", len(msg)) + msg)
p.stdin.flush()
length = struct.unpack("=I", p.stdout.read(4))[0]
reply = json.loads(p.stdout.read(length))
p.stdin.close()
print("native host replied:", reply)
assert reply.get("id") == 1 and reply.get("ok") and reply.get("version") and reply.get("ytdlp_version"), reply
assert reply.get("installed") == host.lower().endswith(".exe"), reply
assert p.wait(timeout=60) == 0, "host did not exit when stdin closed"
