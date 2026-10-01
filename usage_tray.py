"""
Windows-Taskleisten-Icon fuer Claude, Codex und Grok.

Claude: OAuth-Token aus ~/.claude/.credentials.json, ein minimaler Request
(max_tokens=1, Haiku) und die anthropic-ratelimit-unified-* Header.
Codex: letzter rate_limits-Schnappschuss in der neuesten Session-Datei
unter ~/.codex/sessions (5h = primary, 7d = secondary).
Grok: Wochenquote von demselben Billing-Endpunkt wie /usage.
Eine 5h-Session gibt es bei Grok nicht.
"""

import json
import os
import threading
import time
from datetime import datetime

import requests
from PIL import Image, ImageDraw
import pystray

CRED_PATH = os.path.expanduser(r"~\.claude\.credentials.json")
CODEX_SESSIONS = os.path.expanduser(r"~\.codex\sessions")
GROK_AUTH = os.path.expanduser(r"~\.grok\auth.json")
GROK_VERSION = os.path.expanduser(r"~\.grok\version.json")
GROK_BILLING_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
POLL_SECONDS = 300
MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

_lock = threading.Lock()
_state = {
    "error": "startet...",
    "claude_error": None,
    "codex_error": None,
    "grok_error": None,
    "five_h": None,
    "seven_d": None,
    "codex": None,
    "grok": None,
}


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


def _as_util(value):
    if value is None:
        return None
    return float(value) / 100.0


def _as_int(value):
    if value is None:
        return None
    return int(value)


def parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _newest_rollouts(limit=8):
    found = []
    if not os.path.isdir(CODEX_SESSIONS):
        return found
    for dirpath, _, files in os.walk(CODEX_SESSIONS):
        for name in files:
            if not (name.startswith("rollout-") and name.endswith(".jsonl")):
                continue
            path = os.path.join(dirpath, name)
            try:
                found.append((os.path.getmtime(path), path))
            except OSError:
                continue
    found.sort(reverse=True)
    return found[:limit]


def _last_rate_limits(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, None
    chunk = 4_000_000
    pos = size
    scanned = 0
    while pos > 0 and scanned < 16_000_000:
        take = min(chunk, pos)
        pos -= take
        with open(path, "rb") as f:
            f.seek(pos)
            data = f.read(take)
        if pos > 0:
            cut = data.find(b"\n")
            if cut != -1:
                data = data[cut + 1:]
        found = None
        found_ts = None
        for line in data.splitlines():
            if b'"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            rl = payload.get("rate_limits")
            primary = rl.get("primary") if isinstance(rl, dict) else None
            if isinstance(primary, dict) and primary.get("used_percent") is not None:
                found = rl
                found_ts = obj.get("timestamp")
        if found is not None:
            return found_ts, found
        scanned += take
    return None, None


def fetch_codex_usage():
    rollouts = _newest_rollouts()
    if not rollouts:
        return {"available": False, "error": "keine Codex-Session"}
    for mtime, path in rollouts:
        ts, rl = _last_rate_limits(path)
        if not rl:
            continue
        primary = rl["primary"]
        secondary = rl.get("secondary") if isinstance(rl.get("secondary"), dict) else {}
        return {
            "available": True,
            "five_h_util": _as_util(primary.get("used_percent")),
            "five_h_reset": _as_int(primary.get("resets_at")),
            "seven_d_util": _as_util(secondary.get("used_percent")),
            "seven_d_reset": _as_int(secondary.get("resets_at")),
            "sampled_at": parse_iso(ts) or int(mtime),
        }
    return {"available": False, "error": "keine Codex-Quote in den Sessions"}


def load_grok_token():
    with open(GROK_AUTH, encoding="utf-8") as f:
        auth = json.load(f)
    if isinstance(auth, dict) and isinstance(auth.get("key"), str):
        return auth["key"]
    best_key = None
    best_exp = ""
    values = auth.values() if isinstance(auth, dict) else ()
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("key"), str):
            continue
        exp = value.get("expires_at") or ""
        if best_key is None or exp > best_exp:
            best_key = value["key"]
            best_exp = exp
    if not best_key:
        raise RuntimeError("kein Grok-Token")
    return best_key


def grok_client_version():
    try:
        with open(GROK_VERSION, encoding="utf-8") as f:
            return json.load(f).get("version") or "0.0.0"
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


def fetch_grok_usage():
    token = load_grok_token()
    r = requests.get(
        GROK_BILLING_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "x-grok-client-version": grok_client_version(),
            "x-grok-client-surface": "grok-build",
        },
        timeout=15,
    )
    r.raise_for_status()
    cfg = (r.json() or {}).get("config") or {}
    if cfg.get("creditUsagePercent") is None:
        return {"available": False, "error": "keine Wochenquote"}
    period = cfg.get("currentPeriod") or {}
    products = []
    for row in cfg.get("productUsage") or []:
        if isinstance(row, dict) and row.get("usagePercent") is not None:
            products.append({
                "name": row.get("product") or "?",
                "util": _as_util(row["usagePercent"]),
            })
    return {
        "available": True,
        "seven_d_util": _as_util(cfg.get("creditUsagePercent")),
        "seven_d_reset": parse_iso(period.get("end")),
        "products": products,
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


def fmt_datetime(ts):
    if ts is None:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%d.%m. %H:%M")


def color_for(util):
    if util is None:
        return (128, 128, 128)
    if util < 0.7:
        return (60, 170, 60)
    if util < 0.9:
        return (230, 160, 30)
    return (210, 50, 50)


def make_icon(utils):
    size = 64
    n = max(len(utils), 1)
    gap = 3
    bar_w = max(4, (size - 8 - gap * (n - 1)) // n)
    total = n * bar_w + (n - 1) * gap
    x0 = (size - total) // 2
    top = 4
    bottom = size - 4
    full_h = bottom - top

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def draw_bar(x, util):
        d.rectangle([x, top, x + bar_w, bottom], outline=(90, 90, 90, 255), width=2)
        if util is not None:
            h = int(full_h * min(max(util, 0.0), 1.0))
            if h > 0:
                d.rectangle([x, bottom - h, x + bar_w, bottom], fill=color_for(util))

    for i, util in enumerate(utils):
        draw_bar(x0 + i * (bar_w + gap), util)
    return img


def _pct(util):
    if util is None:
        return "?"
    return f"{util * 100:.0f}%"


def _line(name, util, reset):
    if util is None:
        return f"{name}: —"
    return f"{name}: {_pct(util)}   reset {fmt_delta(reset)}"


def tooltip_text():
    with _lock:
        s = dict(_state)
    if s.get("error") == "startet...":
        return "Usage - startet..."
    parts = []
    fh = s.get("five_h") or {}
    sd = s.get("seven_d") or {}
    codex = s.get("codex") or {}
    grok = s.get("grok") or {}
    if s.get("claude_error"):
        parts.append("C Fehler")
    else:
        bits = []
        if fh.get("five_h_util") is not None:
            bits.append(f"5h {_pct(fh['five_h_util'])}")
        if sd.get("seven_d_util") is not None:
            bits.append(f"7d {_pct(sd['seven_d_util'])}")
        if bits:
            parts.append("C " + " ".join(bits))
    if s.get("codex_error"):
        parts.append("X Fehler")
    else:
        bits = []
        if codex.get("five_h_util") is not None:
            bits.append(f"5h {_pct(codex['five_h_util'])}")
        if codex.get("seven_d_util") is not None:
            bits.append(f"7d {_pct(codex['seven_d_util'])}")
        if bits:
            parts.append("X " + " ".join(bits))
    if s.get("grok_error"):
        parts.append("G Fehler")
    elif grok.get("seven_d_util") is not None:
        parts.append(f"G 7d {_pct(grok['seven_d_util'])}")
    return " | ".join(parts)[:120] or "Usage"


def _product_line(products):
    labels = {"GrokBuild": "Build", "GrokVoice": "Voice"}
    parts = []
    for row in products or []:
        if row.get("util") is None:
            continue
        parts.append(f"{labels.get(row['name'], row['name'])} {_pct(row['util'])}")
    if not parts:
        return None
    return "Grok Anteile: " + ", ".join(parts)


def menu():
    with _lock:
        s = dict(_state)
    fh = s.get("five_h") or {}
    sd = s.get("seven_d") or {}
    codex = s.get("codex") or {}
    grok = s.get("grok") or {}
    lines = []
    if s.get("claude_error"):
        lines.append("Claude: " + s["claude_error"][:80])
    else:
        lines.append(_line("Claude 5h", fh.get("five_h_util"), fh.get("five_h_reset")))
        lines.append(_line("Claude 7d", sd.get("seven_d_util"), sd.get("seven_d_reset")))
    if s.get("codex_error"):
        lines.append("Codex: " + s["codex_error"][:80])
    else:
        lines.append(_line("Codex 5h", codex.get("five_h_util"), codex.get("five_h_reset")))
        lines.append(_line("Codex 7d", codex.get("seven_d_util"), codex.get("seven_d_reset")))
        if codex.get("sampled_at"):
            lines.append("Codex-Stand: " + fmt_datetime(codex["sampled_at"]))
    if s.get("grok_error"):
        lines.append("Grok: " + s["grok_error"][:80])
    else:
        lines.append(_line("Grok 7d", grok.get("seven_d_util"), grok.get("seven_d_reset")))
        product = _product_line(grok.get("products"))
        if product:
            lines.append(product)
    for line in lines:
        yield pystray.MenuItem(line, None, enabled=False)
    yield pystray.Menu.SEPARATOR
    yield pystray.MenuItem("Jetzt aktualisieren", force_refresh)
    yield pystray.MenuItem("Beenden", quit_app)


def poll_loop(icon):
    while True:
        time.sleep(POLL_SECONDS)
        _refresh_state(icon)
        icon.title = tooltip_text()


def force_refresh(icon, item):
    threading.Thread(target=lambda: _one_shot(icon), daemon=True).start()


def _one_shot(icon):
    _refresh_state(icon)
    icon.title = tooltip_text()


def _take(result):
    if not result.get("available", True) and result.get("error"):
        return None, result["error"][:120]
    return result, None


def _refresh_state(icon):
    claude_error = None
    codex_error = None
    grok_error = None
    five_h = None
    seven_d = None
    codex = None
    grok = None

    try:
        data = fetch_usage()
        five_h = {
            "five_h_util": data["five_h_util"],
            "five_h_reset": data["five_h_reset"],
        }
        seven_d = {
            "seven_d_util": data["seven_d_util"],
            "seven_d_reset": data["seven_d_reset"],
        }
    except Exception as e:
        claude_error = str(e)[:120]

    try:
        codex, codex_error = _take(fetch_codex_usage())
    except Exception as e:
        codex_error = str(e)[:120]

    try:
        grok, grok_error = _take(fetch_grok_usage())
    except Exception as e:
        grok_error = str(e)[:120]

    if claude_error and codex_error and grok_error:
        combined = "alle Quellen fehlgeschlagen"
    else:
        combined = None

    with _lock:
        _state["error"] = combined
        _state["claude_error"] = claude_error
        _state["codex_error"] = codex_error
        _state["grok_error"] = grok_error
        _state["five_h"] = five_h
        _state["seven_d"] = seven_d
        _state["codex"] = codex
        _state["grok"] = grok

    icon.icon = make_icon([
        five_h["five_h_util"] if five_h else None,
        seven_d["seven_d_util"] if seven_d else None,
        codex.get("five_h_util") if codex else None,
        codex.get("seven_d_util") if codex else None,
        grok.get("seven_d_util") if grok else None,
    ])


def quit_app(icon, item):
    icon.stop()


def main():
    icon = pystray.Icon(
        "claude-codex-usage",
        icon=make_icon([None, None, None, None, None]),
        title="Usage - startet...",
        menu=pystray.Menu(menu),
    )
    _refresh_state(icon)
    icon.title = tooltip_text()
    threading.Thread(target=poll_loop, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
