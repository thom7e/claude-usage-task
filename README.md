# claude-usage-tray

Windows-Taskleisten-Icon fuer die live Claude-Code Nutzung und lokale Codex-Nutzung.

- Claude: 5h-Session-Limit und 7-Tage-(Weekly)-Limit aus den Anthropic-RateLimit-Headern.
- Codex: lokal gespeicherte Token-Nutzung aus `~/.codex/state_5.sqlite`.

## Funktionsweise

Liest den OAuth-Access-Token aus `~/.claude/.credentials.json` (wird von Claude Code selbst verwaltet/erneuert) und schickt periodisch einen minimalen Request (`max_tokens=1`, Modell Haiku) an `https://api.anthropic.com/v1/messages`. Ausgewertet werden die `anthropic-ratelimit-unified-5h-utilization` / `-7d-utilization` Response-Header sowie die zugehoerigen `-reset` Timestamps — dieselben Werte, die auch die offizielle Anzeige nutzt.

Jeder Poll kostet minimal Quota (1 Output-Token). Standardintervall: alle 5 Minuten.

Codex wird ohne Netzwerk-Request aus der lokalen Codex-Datenbank gelesen. Angezeigt werden die lokal gespeicherten Token fuer heute, 7 Tage und insgesamt. Das ist keine offizielle Account-Quota, sondern eine lokale Nutzungsuebersicht der auf diesem Rechner vorhandenen Codex-Threads.

Wichtig: Codex-Restquote/Reset-Zeit wird derzeit nicht angezeigt, weil diese Werte nicht stabil in den lokalen Codex-Dateien verfuegbar sind. Die Codex-Anzeige ist deshalb ein lokaler Nutzungszaehler, keine Limit-Anzeige.

## Anzeige

Icon: drei vertikale Balken (Claude 5h, Claude 7d, Codex heute). Claude zeigt echte Limit-Auslastung; Codex normalisiert die heutigen lokalen Tokens gegen `CODEX_DAILY_WARN_TOKENS` (Standard: 10 Mio.).

Tray-Tooltip: kurze stabile Windows-Anzeige mit Claude-Prozentwerten, Reset-Zeit und Codex-Tokens heute.

Rechtsklick-Menü: "Jetzt aktualisieren", "Beenden".

## Setup

```
pip install -r requirements.txt
python usage_tray.py
```

Voraussetzung: eine aktive Claude-Code-Session/-Anmeldung auf dem Rechner (`~/.claude/.credentials.json` muss existieren).

## Autostart (Windows)

`start_silent.vbs` startet die App ohne Konsolenfenster via `pythonw.exe`. Für Autostart eine Verknüpfung darauf in den Ordner `shell:startup` legen (Win+R → `shell:startup`).
