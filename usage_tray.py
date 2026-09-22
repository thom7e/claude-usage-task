"""
Windows-Taskleisten-Icon fuer Claude-Code Session- (5h) und Weekly- (7d) Usage.

Liest den OAuth-Token aus ~/.claude/.credentials.json und schickt periodisch
einen minimalen Request (max_tokens=1, Haiku) an die Anthropic-API, um die
anthropic-ratelimit-unified-* Response-Header auszulesen. Das sind dieselben
Werte, die auch die offizielle Anzeige nutzt.

Jeder Poll kostet ein winziges bisschen Quota (1 Output-Token). Bei POLL_SECONDS=300
sind das ~288 Requests/Tag - vernachlaessigbar gegenueber echter Nutzung, aber nicht null.
"""

import io
import json
import os
import threading
import time
from datetime import datetime

import requests
from PIL import Image, ImageDraw
import pystray

CRED_PATH = os.path.expanduser(r"~\.claude\.credentials.json")
POLL_SECONDS = 300
MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

_lock = threading.Lock()
_state = {"error": "startet...", "five_h": None, "seven_d": None}


def load_token():
    with open(CRED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["claudeAiOauth"]["accessToken"]


def fetch_usage():
    token = load_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }
    r = requests.post(API_URL, headers=headers, json=body, timeout=15)
    h = r.headers

    def pct(key):
        v = h.get(key)
        return float(v) if v is not None else None

    def reset(key):
        v = h.get(key)
        return int(v) if v is not None else None

    return {
        "five_h_util": pct("anthropic-ratelimit-unified-5h-utilization"),
        "five_h_reset": reset("anthropic-ratelimit-unified-5h-reset"),
        "seven_d_util": pct("anthropic-ratelimit-unified-7d-utilization"),
        "seven_d_reset": reset("anthropic-ratelimit-unified-7d-reset"),
        "status": h.get("anthropic-ratelimit-unified-status"),
    }


def fmt_delta(ts):
    if ts is None:
        return "?"
    secs = ts - time.time()
    if secs <= 0:
        return "jetzt"
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d}d {h}h"
    return f"{h}h {m}m"


def color_for(util):
    if util is None:
        return (128, 128, 128)
    if util < 0.7:
        return (60, 170, 60)
    if util < 0.9:
        return (230, 160, 30)
    return (210, 50, 50)


def make_icon(five_h, seven_d):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    bar_w = 22
    gap = 8
    margin_x = (size - (2 * bar_w + gap)) // 2
    top = 4
    bottom = size - 4
    full_h = bottom - top

    def draw_bar(x, util, label_color):
        d.rectangle([x, top, x + bar_w, bottom], outline=(90, 90, 90, 255), width=2)
        if util is not None:
            h = int(full_h * min(util, 1.0))
            d.rectangle([x, bottom - h, x + bar_w, bottom], fill=label_color)

    draw_bar(margin_x, five_h, color_for(five_h))
    draw_bar(margin_x + bar_w + gap, seven_d, color_for(seven_d))

    return img


def tooltip_text():
    with _lock:
        s = dict(_state)
    if s.get("error"):
        return f"Claude Usage - Fehler: {s['error']}"
    fh = s["five_h"]
    sd = s["seven_d"]
    parts = ["Claude Code Usage"]
    if fh:
        parts.append(
            f"5h-Session: {fh['five_h_util']*100:.0f}%  (reset in {fmt_delta(fh['five_h_reset'])})"
        )
    if sd:
        parts.append(
            f"Weekly (7d): {sd['seven_d_util']*100:.0f}%  (reset in {fmt_delta(sd['seven_d_reset'])})"
        )
    return "\n".join(parts)


def poll_loop(icon):
    while True:
        try:
            data = fetch_usage()
            with _lock:
                _state["error"] = None
                _state["five_h"] = {
                    "five_h_util": data["five_h_util"],
                    "five_h_reset": data["five_h_reset"],
                }
                _state["seven_d"] = {
                    "seven_d_util": data["seven_d_util"],
                    "seven_d_reset": data["seven_d_reset"],
                }
            icon.icon = make_icon(data["five_h_util"], data["seven_d_util"])
        except Exception as e:
            with _lock:
                _state["error"] = str(e)[:120]
            icon.icon = make_icon(None, None)
        icon.title = tooltip_text()
        time.sleep(POLL_SECONDS)


def force_refresh(icon, item):
    threading.Thread(target=lambda: _one_shot(icon), daemon=True).start()


def _one_shot(icon):
    try:
        data = fetch_usage()
        with _lock:
            _state["error"] = None
            _state["five_h"] = {
                "five_h_util": data["five_h_util"],
                "five_h_reset": data["five_h_reset"],
            }
            _state["seven_d"] = {
                "seven_d_util": data["seven_d_util"],
                "seven_d_reset": data["seven_d_reset"],
            }
        icon.icon = make_icon(data["five_h_util"], data["seven_d_util"])
    except Exception as e:
        with _lock:
            _state["error"] = str(e)[:120]
    icon.title = tooltip_text()


def quit_app(icon, item):
    icon.stop()


def main():
    icon = pystray.Icon(
        "claude-usage",
        icon=make_icon(None, None),
        title="Claude Usage - startet...",
        menu=pystray.Menu(
            pystray.MenuItem("Jetzt aktualisieren", force_refresh),
            pystray.MenuItem("Beenden", quit_app),
        ),
    )
    threading.Thread(target=poll_loop, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
