# Requirements.md — Türöffner per ESP8266 Long Polling

## 1. Ziel

Es soll eine sichere und einfach bedienbare Lösung entstehen, mit der Airbnb-Gäste eine Eingangstür vor Ort über einen zeitlich begrenzten Zugangscode öffnen können.

Der Gast scannt vor Ort einen QR-Code, öffnet eine HTTPS-Webseite, gibt einen 4- oder besser 6-stelligen Code ein und löst damit über den Server einen Türöffner aus.  
Der Türöffner wird durch ein Relais geschaltet, das von einem ESP8266 ESP-01S angesteuert wird.

## 2. Grundarchitektur

```text
Gast
  ↓ QR-Code
HTTPS-Webseite auf Server
  ↓ Codeeingabe
Backend prüft Code
  ↓ erzeugt Command
ESP8266 hält HTTPS Long-Poll-Verbindung zum Server
  ↓ erhält Command
Relais schaltet Türöffner kurz
```

Wichtig: Der ESP8266 wird nicht aus dem Internet erreichbar gemacht.  
Er baut ausschließlich ausgehende HTTPS-Verbindungen zum Server auf.

## 3. Kommunikationsprinzip

Die bevorzugte Variante ist HTTPS Long Polling.

Ablauf:

```text
1. ESP8266 verbindet sich per HTTPS mit /api/device/wait-command.
2. Server hält den Request offen.
3. Wenn kein gültiger Öffnungsbefehl vorliegt, läuft der Request nach z.B. 30 Sekunden aus.
4. ESP8266 baut danach sofort eine neue Verbindung auf.
5. Wenn ein Gast einen gültigen Code eingibt, antwortet der Server sofort auf den offenen Request.
6. ESP8266 schaltet das Relais für z.B. 1–2 Sekunden.
7. ESP8266 meldet das Ergebnis an den Server zurück.
8. ESP8266 startet wieder den nächsten Long-Poll-Request.
```

Vorteile:

- keine Portfreigabe zur Wohnung nötig
- ESP bleibt hinter NAT/WLAN
- sehr geringe Verzögerung
- Server erkennt über `last_seen`, ob der ESP online ist
- einfacher als MQTT oder WebSocket
- gut mit NGINX/HTTPS betreibbar

## 4. Komponenten

### 4.1 Server

Empfohlener Stack:

```text
Python
FastAPI
SQLite
NGINX als HTTPS Reverse Proxy
```

Für eine einzelne Wohnung reicht SQLite zunächst aus.  

### 4.2 ESP8266

Hardware:

```text
ESP8266 ESP-01S
Relaismodul
separate Stromversorgung für Türöffner
```

Anforderungen:

- verbindet sich mit dem WLAN der Wohnung
- baut ausgehende HTTPS-Verbindung zum Server auf
- authentifiziert sich mit Device Token
- schaltet Relais nur nach gültigem Server-Command
- begrenzt Relais-Impuls hart auf z.B. maximal 3 Sekunden
- startet nach Fehlern automatisch neu bzw. verbindet sich neu
- darf beim Booten das Relais nicht unbeabsichtigt schalten

## 5. API-Endpunkte

### 5.1 Gast: Code prüfen und Öffnung anfordern

```http
POST /api/guest/open
```

Request:

```json
{
  "apartment_id": "apartment-01",
  "code": "483921"
}
```

Server prüft:

- Code existiert
- Code ist aktiv
- aktueller Zeitpunkt liegt innerhalb `valid_from` und `valid_until`
- `used_count < max_uses`
- Rate-Limit nicht überschritten
- Wohnung bzw. Tür ist bekannt
- ESP ist optional online oder Command kann kurz gepuffert werden

Response bei Erfolg:

```json
{
  "status": "accepted",
  "message": "Die Tür wird geöffnet."
}
```

Response bei Fehler:

```json
{
  "status": "denied",
  "message": "Code ungültig oder nicht gültig."
}
```

Hinweis: Fehlermeldungen sollten neutral bleiben. Nicht verraten, ob ein Code falsch, abgelaufen oder gesperrt ist.

---

### 5.2 ESP: Auf Command warten

```http
GET /api/device/wait-command
Authorization: Bearer <device_token>
```

Serververhalten:

- Request bis maximal z.B. 60 Sekunden offen halten
- bei vorhandenem Command sofort antworten
- bei Timeout mit `command: none` antworten
- `last_seen` des Geräts aktualisieren

Response ohne Command:

```json
{
  "command": "none"
}
```

Response mit Command:

```json
{
  "command_id": "cmd_abc123",
  "command": "open",
  "duration_ms": 1500,
  "expires_at": "2026-07-10T14:05:10Z"
}
```

---

### 5.3 ESP: Command-Ergebnis melden

```http
POST /api/device/command-result
Authorization: Bearer <device_token>
```

Request:

```json
{
  "command_id": "cmd_abc123",
  "status": "done",
  "message": "Relay switched for 1500 ms"
}
```

Mögliche Statuswerte:

```text
done
failed
expired
ignored
```

## 6. Datenmodell

### 6.1 access_codes

```text
id
apartment_id
code_hash
valid_from
valid_until
max_uses
used_count
active
booking_reference
guest_name optional
created_at
updated_at
```

Anforderungen:

- Codes nicht im Klartext speichern
- Code-Hash z.B. per HMAC oder bcrypt speichern
- Codes sollten 6-stellig sein
- 4-stellige Codes nur vermeiden oder zusätzlich stark absichern

### 6.2 devices

```text
id
apartment_id
device_name
device_token_hash
last_seen
last_ip
online_status optional
created_at
updated_at
```

### 6.3 door_commands

```text
id
device_id
apartment_id
command
duration_ms
status
created_at
expires_at
delivered_at
acknowledged_at
source
access_code_id optional
```

Statuswerte:

```text
pending
delivered
done
failed
expired
```

Wichtig:

- Öffnungsbefehle müssen kurzlebig sein
- `expires_at` z.B. `created_at + 10 Sekunden`
- ein alter Command darf nicht später plötzlich eine Tür öffnen

### 6.4 access_log

```text
id
apartment_id
access_code_id optional
timestamp
ip_address
user_agent optional
result
reason optional
command_id optional
```

Result-Beispiele:

```text
success
denied
rate_limited
expired
device_offline
```

## 7. Code-Regeln

Empfehlung:

```text
6-stelliger numerischer Code
Gültig ab Check-in-Tag, z.B. 14:00 Uhr
Gültig bis Check-out-Tag, z.B. 11:00 Uhr
optional kleiner Puffer
max_uses begrenzen, z.B. 20–50
```

Sicherheitsmaßnahmen:

- Rate-Limit pro IP
- Rate-Limit pro Apartment
- Sperre nach mehreren Fehlversuchen
- neutrale Fehlermeldungen
- vollständiges Logging
- Admin-Möglichkeit zum Deaktivieren eines Codes

## 8. NGINX-Anforderungen

Der Long-Poll-Endpunkt benötigt eigene Proxy-Einstellungen.

Beispiel:

```nginx
location /api/device/wait-command {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
    proxy_buffering off;
}
```

Anforderungen:

- `proxy_read_timeout` länger als Long-Poll-Timeout
- `proxy_buffering off`
- HTTPS aktiv
- keine unnötige Zwischenspeicherung

## 9. ESP-Verhalten

### 9.1 Normalbetrieb

```text
1. WLAN verbinden
2. HTTPS-Verbindung zu /api/device/wait-command aufbauen
3. Wenn command == none:
     direkt erneut verbinden
4. Wenn command == open:
     prüfen, ob expires_at noch gültig ist
     Relais für duration_ms schalten
     Ergebnis per /api/device/command-result melden
     wieder zu Schritt 2
```

### 9.2 Fehlerverhalten

Bei normalem Long-Poll-Timeout:

```text
sofort neu verbinden
optional 100–500 ms Jitter
```

Bei Netzwerk- oder HTTPS-Fehlern:

```text
exponential backoff bis max. 30s:
1s
2s
5s
10s
30s
```

Danach weiter versuchen.

### 9.3 Relais-Sicherheit

Anforderungen:

- Relais beim Booten nicht unbeabsichtigt schalten
- sicherer Default-Zustand: AUS
- maximale Schaltzeit im ESP hardcoden, z.B. 3000 ms
- Server darf längere Werte senden, ESP begrenzt trotzdem
- separate Stromversorgung für Türöffner
- Freilaufdiode oder geeignetes Relaismodul bei induktiver Last
- Watchdog aktivieren

## 10. Admin-Funktionen

Benötigte Funktionen:

- Code erzeugen
- Zeitraum setzen
- Code deaktivieren
- Code löschen oder archivieren
- Code-Nutzung anzeigen
- Zugriffslog anzeigen
- ESP-Status anzeigen
- letzte Verbindung anzeigen
- manuelles Öffnen auslösen
- Command-Status anzeigen

Optional:

- iCal-/Airbnb-Kalenderimport
- automatische Code-Erzeugung aus Buchungen
- Reinigungskraft-Code
- Handwerker-Code
- Benachrichtigung bei Türöffnung
- Offline-/Störungsalarm

## 11. Statusanzeige

Der Server kann den ESP-Status aus `last_seen` ableiten.

Beispiel:

```text
last_seen < 90 Sekunden  → online
last_seen >= 90 Sekunden → offline / Verbindung gestört
```

In der Admin-Oberfläche anzeigen:

```text
Gerät: Haustür
Status: online
Letzter Kontakt: vor 8 Sekunden
Letzter erfolgreicher Öffnungsbefehl: 2026-07-10 14:03
```

## 12. Fallback-Anforderungen

Da es um Airbnb-Gäste geht, muss ein Notfallkonzept vorhanden sein.

Erforderlich:

- klassischer Schlüssel oder alternative Zugangsmöglichkeit
- Möglichkeit zur manuellen Öffnung durch Admin
- klare Anleitung für Gäste bei Problemen
- Möglichkeit zum Neustart von ESP/Stromversorgung
- Erkennung, wenn ESP offline ist

Nicht akzeptabel:

```text
Gast steht bei WLAN-/Server-/ESP-Ausfall ohne Alternative vor verschlossener Tür.
```

## 13. Sicherheitsanforderungen

- ESP nicht öffentlich erreichbar machen
- keine Router-Portfreigabe zum ESP
- ausschließlich ausgehende HTTPS-Verbindung vom ESP zum Server
- Device Token lang und zufällig erzeugen
- Device Token nicht im Frontend verwenden
- Gäste-Code und Device Token strikt trennen
- Zugangscodes nicht im Klartext speichern
- Rate-Limits einbauen
- Logs schreiben
- Admin-Bereich schützen
- Commands kurzlebig machen
- Relais-Schaltzeit server- und esp-seitig begrenzen

## 14. Designentscheidungen

- SQLite ?
- ESP8266 ESP-01S via Platformio
- 6-stellige Codes
- genaue Check-in-/Check-out-Zeiten
- Admin-UI mit SPA
- User-UI (Code-Eingabe) als schön, moderne, einfache HTML mit Hintergrundbild 
- Benachrichtigung bei erfolgreicher Öffnung
- Integration mit iCal später

# Quellcodeauteilung
- /admin-ui: SPA mit code zur Verwaltung der Codes (anlegen/bearbeiten/löschen etc...)
- /guest-ui:   HTML-Seiten zur Code-Eingabe für den Nutzer (Ziel des QR-Codes)
- /api: Fast-API code mit endpunkten für alles
- /esp8266:   Enthält den Code (platformio) für den Controller
