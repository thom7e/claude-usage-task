# claude-usage-tray

Windows-Taskleisten-Icon fuer die live Claude-Code Nutzung: 5h-Session-Limit und 7-Tage-(Weekly)-Limit.

## Funktionsweise

Liest den OAuth-Access-Token aus `~/.claude/.credentials.json` (wird von Claude Code selbst verwaltet/erneuert) und schickt periodisch einen minimalen Request (`max_tokens=1`, Modell Haiku) an `https://api.anthropic.com/v1/messages`. Ausgewertet werden die `anthropic-ratelimit-unified-5h-utilization` / `-7d-utilization` Response-Header sowie die zugehoerigen `-reset` Timestamps — dieselben Werte, die auch die offizielle Anzeige nutzt.

Jeder Poll kostet minimal Quota (1 Output-Token). Standardintervall: alle 5 Minuten.

## Anzeige

Icon: zwei vertikale Balken (links 5h-Session, rechts 7d-Weekly), Fuellstand = Auslastung, Farbe gruen/gelb/rot je nach Schwelle (<70% / <90% / >=90%).

Tooltip beim Hover: exakte Prozentwerte + Reset-Zeit ("in Xh Ym" bzw. "in Xd Xh").

Rechtsklick-Menü: "Jetzt aktualisieren", "Beenden".

## Setup

```
pip install -r requirements.txt
python usage_tray.py
```

Voraussetzung: eine aktive Claude-Code-Session/-Anmeldung auf dem Rechner (`~/.claude/.credentials.json` muss existieren).

## Autostart (Windows)

`start_silent.vbs` startet die App ohne Konsolenfenster via `pythonw.exe`. Für Autostart eine Verknüpfung darauf in den Ordner `shell:startup` legen (Win+R → `shell:startup`).
