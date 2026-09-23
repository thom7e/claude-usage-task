"""
Windows-Taskleisten-Icon fuer Claude-Code Session- (5h), Weekly- (7d)
und lokale Codex-Nutzung.

Liest den OAuth-Token aus ~/.claude/.credentials.json und schickt periodisch
einen minimalen Request (max_tokens=1, Haiku) an die Anthropic-API, um die
anthropic-ratelimit-unified-* Response-Header auszulesen. Das sind dieselben
Werte, die auch die offizielle Anzeige nutzt.

Jeder Poll kostet ein winziges bisschen Quota (1 Output-Token). Bei POLL_SECONDS=300
sind das ~288 Requests/Tag - vernachlaessigbar gegenueber echter Nutzung, aber nicht null.

Codex wird lokal aus ~/.codex/state_5.sqlite gelesen. Das ist keine Account-Quota,
sondern die lokal von Codex gespeicherte Token-Nutzung je Thread.
"""

import io
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw
import pystray

CRED_PATH = os.path.expanduser(r"~\.claude\.credentials.json")
CODEX_STATE_DB = os.path.expanduser(r"~\.codex\state_5.sqlite")
CODEX_DAILY_WARN_TOKENS = int(os.environ.get("CODEX_DAILY_WARN_TOKENS", "10000000"))
POLL_SECONDS = 300
MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

_lock = threading.Lock()
_state = {
    "error": "startet...",
    "claude_error": None,
    "codex_error": None,
    "five_h": None,
    "seven_d": None,
    "codex": None,
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


def start_of_today_ts():
    now = datetime.now()
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def fetch_codex_usage():
    if not os.path.exists(CODEX_STATE_DB):
        return {"available": False, "error": f"nicht gefunden: {CODEX_STATE_DB}"}

    today_ts = start_of_today_ts()
    seven_days_ts = int((datetime.now() - timedelta(days=7)).timestamp())
    db_uri = f"file:{CODEX_STATE_DB}?mode=ro"

    with sqlite3.connect(db_uri, uri=True, timeout=2) as con:
        con.row_factory = sqlite3.Row
        summary = con.execute(
            """
            select
                coalesce(sum(tokens_used), 0) as total_tokens,
                coalesce(sum(case when updated_at >= ? then tokens_used else 0 end), 0) as today_tokens,
                coalesce(sum(case when updated_at >= ? then tokens_used else 0 end), 0) as seven_d_tokens,
                count(*) as thread_count,
                coalesce(sum(case when updated_at >= ? then 1 else 0 end), 0) as today_threads,
                coalesce(sum(case when updated_at >= ? then 1 else 0 end), 0) as seven_d_threads
            from threads
            where model_provider = 'openai'
            """,
            (today_ts, seven_days_ts, today_ts, seven_days_ts),
        ).fetchone()
        latest = con.execute(
            """
            select title, updated_at, tokens_used
            from threads
            where model_provider = 'openai'
            order by updated_at desc
            limit 1
            """
        ).fetchone()

    return {
        "available": True,
        "total_tokens": int(summary["total_tokens"]),
        "today_tokens": int(summary["today_tokens"]),
        "seven_d_tokens": int(summary["seven_d_tokens"]),
        "thread_count": int(summary["thread_count"]),
        "today_threads": int(summary["today_threads"]),
        "seven_d_threads": int(summary["seven_d_threads"]),
        "latest_title": latest["title"] if latest else None,
        "latest_updated": int(latest["updated_at"]) if latest else None,
        "latest_tokens": int(latest["tokens_used"]) if latest else 0,
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


def fmt_tokens(tokens):
    if tokens is None:
        return "?"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}k"
    return str(tokens)


def color_for(util):
    if util is None:
        return (128, 128, 128)
    if util < 0.7:
        return (60, 170, 60)
    if util < 0.9:
        return (230, 160, 30)
    return (210, 50, 50)


def codex_util(codex):
    if not codex or not codex.get("available") or CODEX_DAILY_WARN_TOKENS <= 0:
        return None
    return min(codex["today_tokens"] / CODEX_DAILY_WARN_TOKENS, 1.0)


def make_icon(five_h, seven_d, codex=None):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    bar_w = 14
    gap = 6
    margin_x = (size - (3 * bar_w + 2 * gap)) // 2
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
    codex_activity = codex_util(codex)
    draw_bar(margin_x + 2 * (bar_w + gap), codex_activity, color_for(codex_activity))

    return img


def tooltip_text():
    with _lock:
        s = dict(_state)
    if s.get("error"):
        return f"Claude + Codex Usage - Fehler: {s['error']}"
    fh = s["five_h"]
    sd = s["seven_d"]
    codex = s.get("codex")
    parts = ["Claude + Codex Usage"]
    if s.get("claude_error"):
        parts.append(f"Claude: Fehler: {s['claude_error']}")
    if fh:
        parts.append(
            f"Claude 5h: {fh['five_h_util']*100:.0f}%  (reset in {fmt_delta(fh['five_h_reset'])})"
        )
    if sd:
        parts.append(
            f"Claude 7d: {sd['seven_d_util']*100:.0f}%  (reset in {fmt_delta(sd['seven_d_reset'])})"
        )
    if s.get("codex_error"):
        parts.append(f"Codex: Fehler: {s['codex_error']}")
    elif codex and codex.get("available"):
        parts.append(
            f"Codex heute: {fmt_tokens(codex['today_tokens'])} Tokens in {codex['today_threads']} Threads"
        )
        parts.append(
            f"Codex 7d: {fmt_tokens(codex['seven_d_tokens'])} Tokens in {codex['seven_d_threads']} Threads"
        )
        parts.append(f"Codex gesamt lokal: {fmt_tokens(codex['total_tokens'])} Tokens")
        if codex.get("latest_title"):
            title = codex["latest_title"]
            if len(title) > 50:
                title = title[:47] + "..."
            parts.append(
                f"Letzter Codex-Thread: {fmt_tokens(codex['latest_tokens'])} Tokens, {fmt_datetime(codex['latest_updated'])}"
            )
            parts.append(title)
    return "\n".join(parts)


def tray_title_text():
    with _lock:
        s = dict(_state)
    if s.get("error"):
        return "Claude + Codex Usage - Fehler"

    parts = []
    fh = s.get("five_h")
    sd = s.get("seven_d")
    codex = s.get("codex")

    if fh and fh.get("five_h_util") is not None:
        parts.append(f"C 5h {fh['five_h_util']*100:.0f}% reset {fmt_delta(fh['five_h_reset'])}")
    if sd and sd.get("seven_d_util") is not None:
        parts.append(f"7d {sd['seven_d_util']*100:.0f}%")
    if codex and codex.get("available"):
        parts.append(f"Codex {fmt_tokens(codex['today_tokens'])} heute")

    if not parts:
        if s.get("claude_error") and s.get("codex_error"):
            return "Claude + Codex Usage - Fehler"
        if s.get("claude_error"):
            return "Claude Fehler | Codex bereit"
        if s.get("codex_error"):
            return "Claude bereit | Codex Fehler"
        return "Claude + Codex Usage"

    return " | ".join(parts)[:120]


def poll_loop(icon):
    while True:
        _refresh_state(icon)
        icon.title = tray_title_text()
        time.sleep(POLL_SECONDS)


def force_refresh(icon, item):
    threading.Thread(target=lambda: _one_shot(icon), daemon=True).start()


def _one_shot(icon):
    _refresh_state(icon)
    icon.title = tray_title_text()


def _refresh_state(icon):
    claude_error = None
    codex_error = None
    five_h = None
    seven_d = None
    codex = None

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
        codex = fetch_codex_usage()
        if not codex.get("available"):
            codex_error = codex.get("error", "nicht verfuegbar")[:120]
    except Exception as e:
        codex_error = str(e)[:120]

    with _lock:
        _state["error"] = claude_error and codex_error
        _state["claude_error"] = claude_error
        _state["codex_error"] = codex_error
        _state["five_h"] = five_h
        _state["seven_d"] = seven_d
        _state["codex"] = codex

    icon.icon = make_icon(
        five_h["five_h_util"] if five_h else None,
        seven_d["seven_d_util"] if seven_d else None,
        codex,
    )


def quit_app(icon, item):
    icon.stop()


def main():
    icon = pystray.Icon(
        "claude-codex-usage",
        icon=make_icon(None, None, None),
        title="Claude + Codex Usage - startet...",
        menu=pystray.Menu(
            pystray.MenuItem("Jetzt aktualisieren", force_refresh),
            pystray.MenuItem("Beenden", quit_app),
        ),
    )
    _refresh_state(icon)
    icon.title = tray_title_text()
    threading.Thread(target=poll_loop, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
