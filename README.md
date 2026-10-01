# claude-usage-tray

Windows-Taskleisten-Icon fuer Claude, Codex und Grok.

- Claude: 5h-Session und 7-Tage-Limit aus den Anthropic-RateLimit-Headern.
- Codex: 5h-Session und 7-Tage-Limit aus dem letzten `rate_limits`-Schnappschuss der neuesten Session unter `~/.codex/sessions`.
- Grok: Wochenquote vom selben Billing-Endpunkt wie `/usage`. Grok hat keine 5h-Session.

## Funktionsweise

Claude liest den OAuth-Access-Token aus `~/.claude/.credentials.json` und schickt periodisch einen minimalen Request (`max_tokens=1`, Modell Haiku) an `https://api.anthropic.com/v1/messages`. Ausgewertet werden `anthropic-ratelimit-unified-5h-utilization` / `-7d-utilization` und die zugehoerigen `-reset` Timestamps.

Jeder Claude-Poll kostet 1 Output-Token. Standardintervall: alle 5 Minuten.

Codex liest lokal, ohne Request. Die Werte schreibt Codex selbst in die Session (`primary` = 5 Stunden, `secondary` = 7 Tage, `used_percent`, `resets_at`). Der Balken zeigt den letzten Schnappschuss, nicht einen Live-Stand. Rechtsklick nennt die Uhrzeit dieses Stands.

Grok liest `~/.grok/auth.json` und fragt `https://cli-chat-proxy.grok.com/v1/billing?format=credits` ab. Angezeigt wird `creditUsagePercent` der laufenden Woche. Der Token wird nicht erneuert; das macht die Grok-CLI selbst.

## Anzeige

Icon: fuenf Balken, von links: Claude 5h, Claude 7d, Codex 5h, Codex 7d, Grok 7d.

Tooltip: `C 5h ..% 7d ..% | X 5h ..% 7d ..% | G 7d ..%`.

Rechtsklick: dieselben Werte mit Reset-Zeit, dazu "Jetzt aktualisieren" und "Beenden".

## Setup

```
pip install -r requirements.txt
python usage_tray.py
```

Voraussetzung: angemeldetes Claude Code (`~/.claude/.credentials.json`), ein Codex-Session-Log und eine Grok-Anmeldung (`~/.grok/auth.json`).

## Autostart (Windows)

`start_silent.vbs` startet die App ohne Konsolenfenster via `pythonw.exe`. Fuer Autostart eine Verknuepfung darauf in den Ordner `shell:startup` legen (Win+R, `shell:startup`).
