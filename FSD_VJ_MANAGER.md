# FSD: Displaywall VJ-Manager v2.0

## 1. Ziel und Scope

Aufbau einer synchronisierten 6-Monitor-Displaywall (3x Raspberry Pi 5, je 2x WQHD)
mit einer webbasierten Verwaltungsoberflaeche. Der VJ-Manager ersetzt die bisherige
einfache Dual-Display-GUI durch eine vollstaendige Loesung mit Canvas-Editor,
Asset-Pool und Masterclock-Synchronisation.

**Einschraenkung:** Nur Bilder und Videos. Kein Web-Content auf HDMI-2-Displays
(Anthias-Limitation: ScreenlyWebview nur auf HDMI-1).

## 2. Hardware-Basis

| Einheit | Hostname | HDMI-1 | HDMI-2 | IP |
|---------|----------|--------|--------|----|
| Head-Pi | `head-pi` | `head-1` | `head-2` | 192.168.193.105 |
| Slave 1 | `slave1-pi` | `slave1-1` | `slave1-2` | TBD |
| Slave 2 | `slave2-pi` | `slave2-1` | `slave2-2` | TBD |

- Plattform: Raspberry Pi 5 (ARM64), Raspberry Pi OS Bookworm
- Monitore: 2560x1440 WQHD, Mischung Landscape/Portrait
- Netzwerk: WLAN (Displaywall-SSID), zukuenftig optional LAN
- Stromversorgung: 5.4V/15A Netzteil (Waveshare MOSFET-Kompensation)

### Hardware-Benennung

6 Ausgaenge, eindeutig und maschinenlesbar:

```
head-1   head-2   slave1-1   slave1-2   slave2-1   slave2-2
```

Format: `<hostname>-<hdmi_nr>`. Wird in `wall_config.json`, GUI und Sync-Protokoll
konsistent verwendet.

## 3. Architektur

### Ist-Zustand (Head-Pi, verifiziert)

```
HDMI-1: Anthias (Docker, CPU 0-1) -> ScreenlyWebview (linuxfb) / mpv (DRM)
HDMI-2: viewer2.py (systemd, CPU 2-3) -> mpv (EGL/DRM, --gpu-context=drm)
```

### Ziel-Zustand (alle 3 Pis)

```
                    ┌─────────────────────┐
                    │   VJ-Manager GUI    │
                    │  (Browser, Port 80) │
                    └─────────┬───────────┘
                              │ HTTP/REST
                    ┌─────────▼───────────┐
                    │  displaywall-mgr.py │
                    │     (Head-Pi)       │
                    │  - REST-API         │
                    │  - Static Files     │
                    │  - wall_config.json │
                    └─────────┬───────────┘
                              │ UDP Broadcast (Port 1666)
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐ ┌─────▼────────┐ ┌────▼─────────┐
     │   Head-Pi     │ │  Slave1-Pi   │ │  Slave2-Pi   │
     │ viewer (x2)   │ │ viewer (x2)  │ │ viewer (x2)  │
     │ mpv + IPC     │ │ mpv + IPC    │ │ mpv + IPC    │
     └───────────────┘ └──────────────┘ └──────────────┘
```

### Entscheidung gegen PocketVJ

PocketVJ wurde evaluiert (siehe Recherche-Bericht). Ergebnis:
- Basiert vollstaendig auf **omxplayer**, der auf Pi 5/Bookworm nicht lauffaehig ist
  (deprecated, keine Broadcom-Legacy-Decoder)
- Projekt seit ~2021 inaktiv, keine Migration zu mpv/gstreamer
- **"oss-sync"** ist omxplayer-sync, ebenfalls nicht Pi-5-kompatibel

**Was wir uebernehmen:** Den Sync-Algorithmus von omxplayer-sync (Jump-ahead-and-wait,
UDP-Broadcast, Median-Filter). Portiert auf mpv JSON IPC.

## 4. Komponenten

### A. Asset-Pool

- Sammelstelle fuer alle Medien (Bilder/Videos)
- Aktuell: Anthias-DB (`screenly.db`) als primaere Asset-Quelle
- Mehrfachzuweisung: Ein Asset kann auf mehreren Monitoren liegen
- Upload weiterhin ueber Anthias Web-UI (Port 80)

### B. Canvas (Raeumliche Anordnung)

- Interaktive Flaeche im Browser (Fabric.js)
- 6 Monitor-Bloecke als Rechtecke, frei verschiebbar
- Rotation pro Block: 0, 90, 180, 270 Grad
- Hardware-Zuweisung per Dropdown: `head-1`, `head-2`, `slave1-1`, etc.
- Positionen entsprechen der realen Aufhaengung an der Wand
- Gespeichert in `wall_config.json`

### C. Monitor-Playlist

- Klick auf Monitor-Block im Canvas oeffnet dessen Playlist
- Assets per Drag&Drop aus dem Pool zuweisen
- Reihenfolge per Drag&Drop aendern
- Dauer pro Asset konfigurierbar (Bilder)
- Sync-Offset pro Monitor in Sekunden (+/-)

### D. Masterclock (Synchronisation)

Portierung des omxplayer-sync-Algorithmus auf mpv:

#### Protokoll

- **Transport:** UDP Broadcast, Port 1666
- **Update-Rate:** 10x/Sekunde (verbessert gegenueber 1x bei omxplayer-sync)
- **Nachrichtenformat (JSON):**

```json
{
  "cmd": "tick",
  "t": 1712345678.500,
  "asset": "intro.mp4",
  "pos": 42.567,
  "idx": 3
}
```

| Feld | Bedeutung |
|------|-----------|
| `cmd` | Befehlstyp: `tick`, `next`, `seek`, `pause` |
| `t` | UTC-Timestamp des Masters (NTP-synchronisiert) |
| `asset` | Aktueller Asset-Name |
| `pos` | Playback-Position in Sekunden |
| `idx` | Index in der Playlist |

#### Sync-Algorithmus (adaptiert von omxplayer-sync)

```
SYNC_TOLERANCE  = 0.05   # 50ms — darunter keine Korrektur
SYNC_GRACE_TIME = 5      # Sekunden Schonfrist nach Korrektur
SPEED_FACTOR    = 0.02   # Sanftes Driften: 1.02x oder 0.98x

Slave-Loop (10x/Sek):
  1. Empfange Master-Tick (UDP)
  2. Lese lokale Position (mpv IPC: get_property time-pos)
  3. Berechne deviation = master_pos - local_pos
  4. Fuege deviation in Median-Deque (maxlen=10)
  5. median_dev = median(deque)
  6. Falls |median_dev| > SYNC_TOLERANCE und Schonfrist abgelaufen:
     a. Falls |median_dev| > 2s: Hard-Seek (seek <master_pos> absolute)
     b. Sonst: Speed-Adjust (set_property speed 1.02 oder 0.98)
  7. Falls Master anderes Asset spielt: Wechsel (loadfile <asset>)
```

**Verbesserungen gegenueber omxplayer-sync:**
- Speed-Adjustment statt Pause-Jump-Wait (keine sichtbaren Stoerungen)
- Master-Timestamp im Paket (Netzwerk-Latenz kompensierbar)
- 10x statt 1x pro Sekunde (schnellere Konvergenz)
- Hard-Seek nur bei grosser Abweichung (>2s)

#### Transition-Sync (Bildwechsel)

Fuer diskrete Uebergaenge (Bild → naechstes Bild) genuegt ein einfacherer Mechanismus:

```json
{"cmd": "next", "asset": "logo.png", "at": 1712345679.000}
```

- Master sendet `next`-Befehl **500ms–1s im Voraus** (kompensiert WLAN-Jitter)
- Slaves warten lokal bis Timestamp `at` erreicht ist, dann `loadfile`
- Praezision haengt nur von NTP-Sync ab (typisch <10ms im LAN)

#### NTP-Synchronisation

- Head-Pi: chrony als NTP-Server (`allow 192.168.193.0/24`)
- Slaves: chrony als Client, Head-Pi als bevorzugte Quelle
- Erwartete Genauigkeit: <10ms ueber WLAN

### mpv JSON IPC Referenz

mpv wird auf allen Displays mit IPC-Socket gestartet:

```bash
mpv --input-ipc-server=/tmp/mpv-head-1.sock --vo=gpu --gpu-context=drm ...
```

Steuerung per Unix-Socket:

| Aktion | mpv IPC Befehl |
|--------|----------------|
| Position lesen | `{"command": ["get_property", "time-pos"]}` |
| Seek (absolut) | `{"command": ["seek", 42.5, "absolute"]}` |
| Pause | `{"command": ["set_property", "pause", true]}` |
| Speed | `{"command": ["set_property", "speed", 1.02]}` |
| Datei laden | `{"command": ["loadfile", "/path/to/file.mp4"]}` |

## 5. Datenstruktur: wall_config.json

```json
{
  "version": 1,
  "canvas": {
    "width": 8000,
    "height": 3000,
    "monitors": [
      {
        "id": "head-1",
        "label": "Display 1",
        "x": 0,
        "y": 0,
        "width": 2560,
        "height": 1440,
        "rotation": 0,
        "output": "head-1"
      },
      {
        "id": "head-2",
        "label": "Display 2",
        "x": 2560,
        "y": 0,
        "width": 1440,
        "height": 2560,
        "rotation": 90,
        "output": "head-2"
      }
    ]
  },
  "playlists": {
    "head-1": [
      {"asset": "firmenlogo.png", "duration": 10},
      {"asset": "promo.mp4", "duration": 0}
    ],
    "head-2": [
      {"asset": "portrait-bild.jpg", "duration": 15}
    ]
  },
  "sync": {
    "enabled": true,
    "master": "head-pi",
    "port": 1666,
    "offsets": {
      "head-1": 0,
      "head-2": 0,
      "slave1-1": 0.5,
      "slave1-2": 0.5
    }
  }
}
```

## 6. Dateien (Ziel-Zustand)

| Datei | Ort (Entwicklung) | Ort (Pi) | Zweck |
|-------|-------------------|----------|-------|
| `displaywall/config.py` | `software/displaywall/` | `/home/head/screenly/displaywall/` | Zentrale Konfiguration |
| `displaywall/db.py` | `software/displaywall/` | gleich | DB-Zugriff (Anthias) |
| `displaywall/status.py` | `software/displaywall/` | gleich | Systemstatus |
| `displaywall/sync.py` | `software/displaywall/` | gleich | **NEU:** Masterclock-Sync |
| `displaywall/wall.py` | `software/displaywall/` | gleich | **NEU:** wall_config.json Logik |
| `viewer2.py` | `software/` | `/home/head/screenly/` | Viewer HDMI-2 (+ Sync-Slave) |
| `viewer.py` | `software/` | `/home/head/screenly/` | **NEU:** Universeller Viewer (alle Displays) |
| `displaywall-mgr.py` | `software/` | `/home/head/screenly/` | Web-Server (REST + Static) |
| `webui/index.html` | `software/webui/` | gleich | HTML |
| `webui/style.css` | `software/webui/` | gleich | CSS |
| `webui/app.js` | `software/webui/` | gleich | **Erweitert:** Canvas + Pool |
| `webui/canvas.js` | `software/webui/` | gleich | **NEU:** Fabric.js Canvas-Editor |

## 7. Waypoints (Implementierungsphasen)

### WP1: wall_config.json Schema + Backend

**Deliverables:**
- `displaywall/wall.py` — Laden/Speichern/Validieren der wall_config.json
- API-Endpoints in `displaywall-mgr.py`:
  - `GET /api/wall` — Konfiguration lesen
  - `POST /api/wall` — Konfiguration schreiben
  - `GET /api/pool` — Alle Assets (Pool)
  - `POST /api/playlist` — Playlist fuer einen Monitor aendern

**Testkriterien:**
- `curl /api/wall` liefert gueltige Konfiguration
- Playlist-Aenderung per API wird in wall_config.json persistiert
- Bestehende Funktionalitaet (viewer2, alte GUI) bleibt erhalten

### WP2: Canvas-GUI (Fabric.js)

**Deliverables:**
- `webui/canvas.js` — Canvas-Editor mit Fabric.js
- Aktualisiertes `webui/index.html` und `webui/style.css`
- Features:
  - 6 Monitor-Bloecke, verschiebbar und rotierbar
  - Asset-Pool-Panel (Liste aller Assets)
  - Drag&Drop: Pool → Monitor-Playlist
  - Klick auf Monitor: Playlist anzeigen/bearbeiten
  - Hardware-Zuweisung per Dropdown am Block

**Testkriterien:**
- GUI laeuft auf Head-Pi (Port 8080), bedienbar vom Laptop
- Monitor-Positionen werden in wall_config.json gespeichert
- Asset-Zuweisung funktioniert (Pool → Monitor → Playlist)

### WP3: Sync-Layer (NTP + UDP + mpv IPC)

**Deliverables:**
- `displaywall/sync.py` — SyncMaster und SyncSlave Klassen
- chrony-Konfiguration fuer Head + Slaves
- viewer2.py Erweiterung: mpv mit IPC-Socket, SyncSlave-Integration
- Systemd-Service fuer Sync-Daemon (oder integriert in Viewer)

**Testkriterien:**
- Zwei Displays auf Head-Pi wechseln gleichzeitig (±50ms)
- Sync-Status in der GUI sichtbar
- Slave-Pi (wenn verfuegbar) synchronisiert sich zum Head

### WP4: WLAN-Latenz-Validierung

**Deliverables:**
- Latenz-Messungen im Displaywall-WLAN unter Last (6x WQHD)
- Dokumentation der Ergebnisse
- Falls noetig: Anpassung der Sync-Parameter oder Empfehlung fuer LAN

**Testkriterien:**
- Jitter-Messung ueber 1 Stunde (UDP Round-Trip)
- Bildwechsel-Synchronitaet messbar <100ms
- Empfehlung: WLAN ausreichend oder LAN noetig?

## 8. Offene Fragen

1. **Asset-Speicherung:** Bleibt Anthias-DB die primaere Quelle, oder migrieren
   wir zu eigener Dateiverwaltung? (Empfehlung: Anthias-DB beibehalten fuer WP1-3,
   spaeter evaluieren)
2. **Slave-Pi Setup:** Laufen Slaves auch mit Anthias oder nur mit Viewer?
   (Empfehlung: Nur Viewer, kein Docker — leichtgewichtiger)
3. **WLAN vs. LAN:** Reicht WLAN fuer den VJ-Effekt? (Wird in WP4 validiert)
4. **Upload-Mechanismus:** Assets auf Slaves verteilen — rsync, NFS, oder
   zentraler Speicher? (Empfehlung: rsync vom Head, getriggert bei Playlist-Aenderung)

## 9. Verworfene Ansaetze

| Ansatz | Warum verworfen |
|--------|----------------|
| PocketVJ als Sync-Unterbau | Basiert auf omxplayer (deprecated), laeuft nicht auf Pi 5, seit 2021 inaktiv |
| PTP (IEEE 1588) | Nanosekunden-Praezision bricht ueber WLAN zusammen, Overkill fuer Bildwechsel |
| WebSocket statt UDP | TCP-Overhead, Handshake noetig — UDP Broadcast ist simpler und schneller |
| Xibo CMS | Kein ARM64-Player |
| Zweite Anthias-Instanz | Wuerde fb0 ueberschreiben (ScreenlyWebview ist hartcodiert auf einen Framebuffer) |
