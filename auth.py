"""Shared secret between the extension and the helper, so web pages can't drive the helper."""
import json
import os
import secrets

EXTENSION_ID = "kcnffalmlnicdbnolfbgonjbjaekcleg"  # pinned by "key" in extension/manifest.json
ORIGIN = f"chrome-extension://{EXTENSION_ID}"
HEADER = "X-Helper-Token"
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def token() -> str:
    """The helper's token, created in config.json on first use. The extension gets it from the native host."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(32)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    return cfg["token"]
