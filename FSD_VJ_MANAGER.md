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

### GUI-Design (PocketVJ-inspiriert)

Die GUI ist von PocketVJs Designsprache inspiriert, aber als komplett eigene Implementierung:

- **Dark Theme:** Hintergrund `#2a2a2e`, Surfaces `#3a3a40`, heller Text
- **Regenbogen-Tab-Leiste (unten):** 3 farbcodierte Tabs — Canvas (orange #f29c33), Sync (blau #4296d2), Devices (rot-orange #f86800). Opacity-/Transform-Transition bei Hover/Active
- **Transport-Toolbar (oben):** Previous, Play, Pause, Stop, Next — SVG-Icons, Hover-Farben pro Funktion (gruen Play, orange Pause, rot Stop, blau Next/Prev). Rechts: Viewer-Status-Dots (gruen/rot mit Glow) + Temperatur
- **Permanente Pool-Sidebar (rechts, 260px):** Immer sichtbar, unabhaengig vom aktiven Tab. Drag&Drop-Quelle fuer alle Ziele (Canvas-Monitore, Playlist, Drop-Zone)
- **Inline-Playlist unter Canvas:** Canvas und Playlist teilen sich einen Tab — kein Tab-Wechsel zum Zuweisen noetig
- **Kombinierter Devices-Tab:** Status + Display-Einstellungen in einer Ansicht. Pi-Karten gruppieren je 2 Displays mit Systeminfos (Temp, Throttle, Uptime, Disk, RAM, MACs, IPs)
- **Alle Abhaengigkeiten lokal:** Fabric.js 5.3.0 liegt als `fabric.min.js` im `webui/`-Verzeichnis. Kein CDN, kein npm, keine Internet-Abhaengigkeit. System-Fonts als Fallback

### A. Asset-Pool (Sidebar)

- Permanente Sidebar rechts, immer sichtbar
- Sammelstelle fuer alle Medien (Bilder/Videos)
- Datenquelle: Anthias-DB (`screenly.db`)
- **Direkter Upload:** Datei-Button + Drag&Drop-Zone in der Sidebar. Multipart-Upload an `/api/upload`, Speicherung in `screenly_assets/`, Eintrag in Anthias-DB
- Mehrfachzuweisung: Ein Asset kann auf mehreren Monitoren liegen
- Drag&Drop aus Pool auf: Canvas-Monitore (direkte Zuweisung), Playlist-Items (einfuegen), Drop-Zone (ans Ende anfuegen)
- **Mouseover-Preview:** Thumbnail-Tooltip zeigt Bild oder Video-Vorschau. Tooltip folgt dem Mauszeiger. Assets werden ueber `/assets/`-Endpoint serviert
- Badge-Typen: Bild (gruen), Video (violett), Web (orange)
- Asset-Liste wird alle 15s automatisch aktualisiert

### B. Canvas (Raeumliche Anordnung)

- Interaktive Flaeche im Browser (Fabric.js 5.3.0, lokal eingebunden)
- 6 Monitor-Bloecke als farbcodierte Rechtecke
- Farbschema pro Monitor: head-1 rot, head-2 hellrot, slave1-1 tuerkis, slave1-2 tuerkis-dunkel, slave2-1 gelb, slave2-2 goldgelb
- Rotation pro Block sichtbar: Symbol im Label (↻ 90°, ↺ 270°, ⇅ 180°)
- Info-Text pro Block: Output-Name, Rotation, Anzahl Assets
- Positionen entsprechen der realen Aufhaengung an der Wand
- Gespeichert in `wall_config.json`

#### B1. Canvas-Modi

Zwei Modi, umschaltbar ueber Buttons in der Canvas-Toolbar:

- **Auswaehlen-Modus (Standard):** Klick auf Monitor waehlt ihn fuer Playlist-Bearbeitung. Canvas wird als verkleinerter Snapshot (PNG, max-height 180px) angezeigt — spart Platz fuer die Playlist. Klick auf Snapshot identifiziert Monitor via Koordinaten-Rueckrechnung
- **Anordnen-Modus:** Monitore frei verschiebbar. Fabric.js Groups (Rect+Label+Info) bewegen sich zusammen. Beim Wechsel zurueck zu Auswaehlen: Positionen werden aus Canvas gelesen, in `wall_config.json` gespeichert, Snapshot erstellt. Visuelles Feedback: orangener Rand + Box-Shadow. **Groessen-Slider:** Breite (300-1200px) und Hoehe (150-900px) per Range-Input einstellbar — Canvas passt sich dynamisch an beliebige Anordnungen an (Querformat, Hochformat, gemischt)
- **Direct-Drop:** Assets aus dem Pool direkt auf Monitor-Bloecke im Canvas ziehen. Drop-Highlight: weisser Rand + erhoehte Opacity

### C. Monitor-Playlist

- Inline unter dem Canvas (gleicher Tab, kein Wechsel noetig)
- Monitor-Selector: Farbcodierte Buttons oberhalb der Playlist
- Assets per Drag&Drop aus dem Pool zuweisen
- Reihenfolge per Drag&Drop aendern (Reorder innerhalb der Liste)
- Dauer pro Asset konfigurierbar (Zahlen-Input, 1-9999s)
- Entfernen-Button (×) pro Item
- Sync-Offset pro Monitor in Sekunden (+/-)
- **Shuffle-Modus:** Toggle-Button (wie CD-Player Zufall-Taste). Persistenter Zustand pro Monitor in `wall_config.json` unter `playback.<monitor>.shuffle`. Viewer waehlt bei aktivem Shuffle zufaelligen Index statt sequenziell
- **Mouseover-Preview:** Wie im Pool — Thumbnail-Tooltip fuer Bilder/Videos
- **Playback-Highlight:** Aktuell spielendes Asset wird gelb hervorgehoben (Rand, Name, Glow), Play-Symbol (▶) statt Nummer. Viewer schreibt `{index, asset}` in `playback_state.json`, GUI pollt `/api/playback` alle 3s. **Match per Asset-Name** (nicht Index), da viewer2 die Anthias-DB-Playlist nutzt und die GUI die wall_config-Playlist zeigt
- **Auto-Save:** Aenderungen werden sofort gespeichert, gruenes "✓ Gespeichert"-Feedback
- Drop-Zone am Ende der Playlist fuer neue Assets

### D. Devices-Tab

Status und Display-Einstellungen kombiniert in einer Ansicht:

- **Pi-Karten:** Eine Karte pro Raspberry Pi, gruppiert 2 Displays
- **Systeminfos:** Temperatur (mit Farbampel), Throttle-Status, Uptime, Disk, RAM
- **Netzwerk:** IP-Adresse, MAC WLAN, MAC Ethernet
- **Display-Einstellungen:** Rotation-Dropdown (0°/90°/180°/270°) pro Display, Aufloesung, Output-Name, Anzahl Assets
- **Viewer-Status:** Gruen/Rot-Dots mit Glow fuer Viewer 1 und 2
- **Offline-Pis:** Ausgegraut mit "Nicht verbunden"-Hinweis (Slave 1/2 noch nicht eingerichtet)

### E. Live-Preview

- Neben der Playlist wird das aktuell abgespielte Asset als Vorschau angezeigt
- Bilder als `<img>`, Videos als `<video muted autoplay loop>` (reduzierte Aufloesung)
- Wechselt automatisch mit dem Playback-Tracker (clientseitiger Timer basierend auf Asset-Dauer)
- Transport-Buttons (Prev/Next) spulen den Tracker und aktualisieren die Preview sofort
- Prev/Next setzen den Timer zurueck — naechster Sync-Zyklus stellt Gleichlauf wieder her

### F. Masterclock (High-Precision Synchronisation)

Die Synchronisation wird von einer einfachen 1s-Quantisierung auf einen **Hardware-Counter-basierten Clock Servo (Software PLL)** umgestellt. Dies garantiert Frame-genaue Bildwechsel unabhängig von WLAN-Jitter.

#### 1. Zeitbasis (Hardware Crystal)
Wir nutzen den **ARM Generic Timer** des Raspberry Pi 5 als ultra-präzise Zeitquelle.
- **Systemquelle:** Der 54MHz Oszillator (Kristall) des Pi 5.
- **Linux API:** `clock_gettime(CLOCK_MONOTONIC_RAW, ...)` liefert die rohe Hardware-Zeit ohne NTP-Sprünge oder Frequenz-Anpassungen des Kernels.
- **Auflösung:** Nanosekunden-Bereich.

#### 2. Synchronisations-Protokoll (Clock Servo)
Anstatt eines "Start"-Befehls in Echtzeit nutzt das System ein Vorhersage-Modell:

1.  **Master-Puls (Head-Pi):** Sendet alle 2 Sekunden ein UDP-Broadcast-Paket (Port 1666):
    ```json
    {
      "cmd": "sync_pulse",
      "master_mono_raw": 1234567890123,
      "next_switch_mono_raw": 1234568000000,
      "asset_idx": 5
    }
    ```
2.  **Slave-Interpolation (Software PLL):**
    - Der Slave empfängt den Puls und vergleicht `master_mono_raw` mit seiner eigenen `local_mono_raw`.
    - Er berechnet das **Frequenz-Verhältnis** (Drift) zum Master.
    - Er berechnet den exakten **Schaltzeitpunkt** in lokaler Hardware-Zeit voraus.
3.  **Das Abfeuern:** Ein hochpriorisierter Thread auf dem Slave wartet (busy-wait in den letzten Microsekunden), bis der lokale System-Counter den berechneten Zielwert erreicht, und löst den `loadfile` Befehl im `mpv` via IPC aus.

#### 3. Vorteile
- **Jitter-Resistenz:** Da der Schaltzeitpunkt im Voraus bekannt ist, spielen Verzögerungen im WLAN (bis zu 500ms) keine Rolle für die Präzision des Bildwechsels.
- **Invariant:** Der System-Counter läuft unabhängig von CPU-Taktänderungen (Turbo/Drosselung).
- **Frame-Sync:** Ermöglicht den Wechsel innerhalb des V-Sync Intervalls der Monitore.

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
| `webui/fabric.min.js` | `software/webui/` | gleich | Fabric.js 5.3.0 (lokal, kein CDN) |
| `displaywall/playback_state.json` | Runtime | gleich | Aktuelle Playback-Position pro Viewer |

## 7. Waypoints (Implementierungsphasen)

### WP1: wall_config.json Schema + Backend — ABGESCHLOSSEN

**Deliverables:**
- `displaywall/wall.py` — Laden/Speichern/Validieren der wall_config.json
- API-Endpoints in `displaywall-mgr.py`:
  - `GET /api/wall` — Konfiguration lesen
  - `POST /api/wall` — Konfiguration schreiben
  - `GET /api/pool` — Alle Assets (Pool)
  - `POST /api/playlist` — Playlist fuer einen Monitor aendern
  - `POST /api/monitor` — Monitor-Einstellungen aendern
  - `POST /api/upload` — Asset-Upload (Multipart)
  - `GET /api/playback` — Aktuelle Playback-Positionen
  - `GET /assets/<file>` — Asset-Dateien servieren (fuer Preview)

**Testkriterien (verifiziert):**
- `curl /api/wall` liefert gueltige Konfiguration
- Playlist-Aenderung per API wird in wall_config.json persistiert
- Upload speichert Datei und traegt in Anthias-DB ein
- Bestehende Funktionalitaet (viewer2, alte GUI) bleibt erhalten

### WP2: Canvas-GUI (Fabric.js) — ABGESCHLOSSEN

**Deliverables:**
- `webui/canvas.js` — Canvas-Editor mit Fabric.js (Zwei-Modus: Auswaehlen/Anordnen)
- `webui/app.js` — Pool-Sidebar, Playlist, Upload, Tab-Navigation, Preview-Tooltips, Playback-Highlight
- `webui/index.html` — PocketVJ-inspiriertes Layout (Transport-Toolbar, Tabs, Sidebar)
- `webui/style.css` — Dark Theme, Regenbogen-Tabs, responsive Layout
- `webui/fabric.min.js` — Fabric.js 5.3.0 lokal
- Features (implementiert):
  - 6 farbcodierte Monitor-Bloecke mit Rotation/Info/Label
  - Auswaehlen-Modus mit Snapshot-Thumbnail, Anordnen-Modus mit Drag
  - Permanente Pool-Sidebar mit Upload (Datei-Button + Drag&Drop)
  - Inline-Playlist unter Canvas (Reorder, Duration, Remove, Shuffle)
  - Direct-Drop: Pool → Canvas-Monitor und Pool → Playlist
  - Mouseover-Preview (Bild/Video-Tooltip) in Pool und Playlist
  - Playback-Highlight: aktuelle Position gelb markiert
  - Transport-Toolbar: Previous, Play, Pause, Stop, Next
  - Devices-Tab: Pi-Karten mit 2 Displays, Systemstatus, Netzwerk-Infos
  - Alle Dependencies lokal (kein Internet noetig)

**Testkriterien (verifiziert):**
- GUI laeuft auf Head-Pi (Port 8080), bedienbar vom Laptop
- Monitor-Positionen werden in wall_config.json gespeichert
- Asset-Zuweisung funktioniert (Pool → Monitor → Playlist)
- Upload funktioniert (Multipart-Parsing ohne cgi-Modul, Python 3.13 kompatibel)
- Preview-Tooltips zeigen Thumbnails bei Mouseover

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

### WP5: HDMI-Capture-Streaming (Live-Vorschau)

**Ziel:** Echtzeit-Vorschau des tatsaechlichen Display-Outputs in der GUI — wie ein professionelles VJ-Tool.

**Ansatz:**
- `ffmpeg -f kmsgrab` oder Framebuffer-Capture (`/dev/fb0`) auf jedem Pi
- Hardware-Encoder `h264_v4l2m2m` (Pi 5) fuer niedrige CPU-Last
- MJPEG-Stream-Endpoint pro Display (z.B. `/api/stream/head-1`)
- Aufloesung stark reduziert (~256x144, 10-15 fps) — Darstellung ist klein
- Alternativ: periodische JPEG-Snapshots (alle 2-3s) statt Stream

**Moegliche Darstellungen:**
- In den Canvas-Monitorbloecken (Fabric.js Image-Objekte)
- Im Devices-Tab als Gesamtuebersicht aller 6 Displays
- Als Vollbild-Preview fuer einzelne Monitore

**Abhaengigkeiten:**
- Erfordert `ffmpeg` auf allen Pis
- CPU-Budget pruefen (Capture + Encode parallel zum Viewer)
- Netzwerk-Bandbreite: 6x MJPEG bei ~50KB/Frame, 15fps = ~4.5 MB/s

**Testkriterien:**
- Stream laeuft stabil ueber 1 Stunde ohne Viewer-Beeintraechtigung
- Latenz Stream → GUI < 1s
- CPU-Last durch Capture < 10% eines Kerns

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
| Pool in separatem Tab | Drag&Drop zwischen Tabs unmoeglich — Pool muss als permanente Sidebar sichtbar sein |
| Canvas und Playlist in separaten Tabs | Klick auf Monitor springt zum Playlist-Tab — desorientierend. Inline-Playlist unter Canvas ist besser |
| Fabric.js: Einzelne Rects statt Groups | Labels bewegen sich nicht mit beim Drag. Groups (Rect+Label+Info) loesen das |
| Canvas immer im Drag-Modus | Klick und Drag kollidieren. Zwei-Modi-Loesung (Auswaehlen/Anordnen) trennt die Interaktionen |
| Separate Status- und Display-Tabs | Redundant: Jeder Pi hostet 2 Displays. Kombinierter Devices-Tab mit Pi-Karten ist uebersichtlicher |
| `cgi.parse_multipart` fuer Upload | In Python 3.13 deprecated. Manuelles Multipart-Parsing mit Boundary-Split und Regex |
| Shuffle als einmaliges Mischen der Liste | User-Feedback: Zufall soll wie CD-Player funktionieren — persistenter Toggle, nicht einmalige Aktion |
| Playback-Highlight per Index | viewer2 liest Anthias-DB-Playlist, GUI zeigt wall_config-Playlist — Indizes stimmen nicht ueberein. Stattdessen Match per Asset-Name |
| Feste Canvas-Hoehe (Seitenverhaeltnis 0.45) | Funktioniert nicht fuer vertikale Monitor-Anordnungen. Erst dynamisch per Bounding-Box, dann manuelle Slider (flexibler) |
