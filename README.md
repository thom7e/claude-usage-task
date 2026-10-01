# claude-usage-tray

Windows-Taskleisten-Icon für Claude, Codex und Grok.

- Claude: 5h-Session und 7-Tage-Limit aus den Anthropic-RateLimit-Headern.
- Codex: 5h-Session und 7-Tage-Limit aus dem letzten `rate_limits`-Schnappschuss der neuesten Session unter `~/.codex/sessions`.
- Grok: Wochenquote vom selben Billing-Endpunkt wie `/usage`. Grok hat keine 5h-Session.

## Funktionsweise

Claude liest den OAuth-Access-Token aus `~/.claude/.credentials.json` und schickt periodisch einen minimalen Request (`max_tokens=1`, Modell Haiku) an `https://api.anthropic.com/v1/messages`. Ausgewertet werden `anthropic-ratelimit-unified-5h-utilization` / `-7d-utilization` und die zugehörigen `-reset` Timestamps.

Jeder Claude-Poll kostet 1 Output-Token. Standardintervall: alle 5 Minuten.

Codex liest lokal, ohne Request. Die Werte schreibt Codex selbst in die Session (`primary` = 5 Stunden, `secondary` = 7 Tage, `used_percent`, `resets_at`). Der Balken zeigt den letzten Schnappschuss, nicht einen Live-Stand.

Grok liest `~/.grok/auth.json` und fragt `https://cli-chat-proxy.grok.com/v1/billing?format=credits` ab. Angezeigt wird `creditUsagePercent` der laufenden Woche. Der Token wird nicht erneuert; das macht die Grok-CLI selbst.

## Anzeige

Icon: fünf Balken, von links: Claude 5h, Claude 7d, Codex 5h, Codex 7d, Grok 7d.

Tooltip, eine Zeile pro Kontingent, maximal 127 Zeichen: `Claude 5h 59% · 3h 25m`.

Rechtsklick: "Jetzt aktualisieren" und "Beenden".

## Setup

```
pip install -r requirements.txt
python usage_tray.py
```

Voraussetzung: angemeldetes Claude Code (`~/.claude/.credentials.json`), ein Codex-Session-Log und eine Grok-Anmeldung (`~/.grok/auth.json`).

## Autostart (Windows)

`start_silent.vbs` startet die App ohne Konsolenfenster via `pythonw.exe`, Pfad relativ zum Skript. Für Autostart eine Verknüpfung darauf in den Ordner `shell:startup` legen (Win+R, `shell:startup`).
