"""End-to-end check on Windows: after install.bat, the registered native host answers the way Chrome expects.

Talks to native_host.bat with Chrome's framing. Run from the repo root.
"""
import json
import os
import struct
import subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

msg = json.dumps({"id": 1, "cmd": "hello"}).encode()
p = subprocess.Popen(["cmd", "/c", os.path.join(BASE, "native_host.bat"), "chrome-extension://smoke-test/"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(struct.pack("=I", len(msg)) + msg)
p.stdin.flush()
length = struct.unpack("=I", p.stdout.read(4))[0]
reply = json.loads(p.stdout.read(length))
p.stdin.close()
print("native host replied:", reply)
assert reply.get("id") == 1 and reply.get("ok") and reply.get("version"), reply
assert p.wait(timeout=60) == 0, "host did not exit when stdin closed"
