# AI Handover & Project Status: Displaywall

## Projektübersicht
Dieses Projekt umfasst die Planung, Hardware-Zusammenstellung und Software-Konfiguration für eine Videowall, bestehend aus 6 WQHD-Monitoren (2560x1440), die von 3 Raspberry Pi 5 Systemen angesteuert werden. 

Die Wand ist gemischt ausgerichtet:
- 4 Monitore im Querformat (Landscape)
- 2 Monitore im Hochformat (Portrait)

**Architektur-Historie:**
1. **Xibo CMS** — verworfen, weil der Xibo-Player nicht fuer ARM64 (Pi 5) verfuegbar ist.
2. **Anthias (Screenly OSE)** — installiert und lauffaehig, aber nur 1 Display pro Pi. Fuer 6 Monitore an 3 Pis ungeeignet.
3. **PiSignage** — empfohlen als naechster Schritt. Unterstuetzt Dual-Display auf Pi 5, Self-Hosted-Server, zentrale Verwaltung. Siehe `PLAYER_EVALUATION.md`.

## Bisherige Meilensteine
- [x] Projekt-Spezifikation (`README.md`) aktualisiert.
- [x] Skript und Anleitung (`HOWTO_ROTATION.md`) fuer die Drehung der Monitore in Wayland erstellt.
- [x] Umstieg auf offizielles Raspberry Pi OS (Debian) (64-bit).
- [x] Recherche und Dokumentation (`SYNC_OPTIONS.md`) zu Frame-genauer Synchronisation.
- [x] **PIVOT 1:** Xibo verworfen (ARM64-inkompatibel). Anthias installiert.
- [x] **PIVOT 2:** Anthias als Single-Display-Limitation erkannt. Player-Evaluation durchgefuehrt (`PLAYER_EVALUATION.md`).
- [x] SSH-Zugriff von WSL2 auf Head-Pi eingerichtet (Key-basiert, passwortlos).
- [x] Stromversorgung analysiert und geloest (Waveshare MOSFET-Verluste, Netzteil auf 5.4V).
- [x] Monitoring-Tool `monitor-power.sh` erstellt.
- [x] Globale KI-Regeln (`~/RULES.md`, `~/.claude/CLAUDE.md`) etabliert.
- [x] Aufloesung auf 2560x1440 korrigiert (via `video=` in cmdline.txt).
- [x] `avoid_warnings=2` in config.txt gesetzt.
- [x] `wlr-randr` und `kanshi` installiert.
- [x] Automatisierte Testsuite `displaywall-test.sh` erstellt (18 PASS, 0 FAIL).
- [x] **Dual-Display geloest:** Viewer-2 (mpv/EGL-DRM) fuer HDMI-A-2, CPU-Pinning, systemd-Service.
- [x] Displaywall Manager Web-GUI (Port 8080) fuer Asset-Zuweisung und Rotation.

## Dateistruktur & Zweck
- `README.md` -> Das generelle Konzept, Hardware-Listen.
- `HOWTO_ANTHIAS.md` -> Anleitung (Step-by-Step) fuer Anthias-Einrichtung.
- `HOWTO_DUAL_DISPLAY.md` -> Anleitung fuer Dual-Display-Setup (Anthias + Viewer-2).
- `HOWTO_ROTATION.md` -> Anleitung zum Drehen der Monitore via SSH.
- `SYNC_OPTIONS.md` -> Analyse der Synchronisations-Optionen.
- `PLAYER_EVALUATION.md` -> Vergleich aller getesteten Player-Loesungen mit Begruendung.
- `STATUS.md` -> Dieses Dokument.
- `sd-card-config/` -> Manuelle Fallback-Dateien für Headless-Boot (falls der Pi-Imager zickt).
- `software/` -> Enthält alle Skripte, die offline auf die Pis übertragen werden.
  - `setup-anthias.sh` -> Wrapper-Skript, das das offizielle Anthias-Setup startet.
  - `rotate-screen.sh` -> Helfer-Skript zum direkten Drehen der Monitore via Wayland (`wlr-randr`).
  - `monitor-power.sh` -> Loggt Spannung, Strom und Throttle-Status in CSV (Diagnose-Tool fuer Waveshare-Gehaeuse).
  - `viewer2.py` -> Standalone-Viewer fuer HDMI-A-2 (mpv-basiert, liest Anthias-DB, Shuffle-Support, Playback-State).
  - `displaywall-mgr.py` -> VJ-Manager Web-Server (REST-API + Static Files, Port 8080).
  - `displaywall-test.sh` -> Automatisierte Testsuite (SSH-basiert, laeuft von WSL2).
  - `displaywall/` -> Python-Package: config.py, db.py, status.py, wall.py.
  - `webui/` -> Frontend: index.html, style.css, app.js, canvas.js, fabric.min.js.
  - `displaywall-agent.py` -> Slave-Agent: REST-API (Port 8081), 2x mpv-Viewer, Asset-Cache.
  - `setup-slave.sh` -> Komplettes Slave-Pi-Setup (Pakete, Display, USB, Agent, systemd).
  - `setup-usb-mount.sh` -> USB-Auto-Mount-Einrichtung (fuer Head und Slaves).

## Erkenntnisse: Stromversorgung (Waveshare Pi5-Module-BOX)
- Die Waveshare-Gehäuse leiten Strom über einen MOSFET (AO4407A) ohne USB-PD auf den Pi durch.
- Bei Standard-5V-Netzteilen kommt zu wenig Spannung am Pi an (~4.4V unter Last) -> Throttling, Abstuerze.
- **Lösung:** Netzteil-Ausgangsspannung auf ~5.4-5.5V hochdrehen.
- `avoid_warnings=2` wird im Produktivbetrieb gesetzt: keine Warnungen auf den Displays. Monitoring laeuft per `monitor-power.sh` (Admin per SSH).
- `usb_max_current_enable=1` hat auf dem Pi 5 keinen Effekt.
- Monitoring-Tool `monitor-power.sh` erstellt fuer Langzeit-Spannungsueberwachung.

## Aktueller Zustand Slave1-Pi (2026-04-12)

- Raspberry Pi 5, Debian Trixie (64-bit), 49 GB frei
- **displaywall-agent.py** laeuft als systemd-Service (Port 8081)
- 2x Viewer-Thread (slave1-1 auf HDMI-A-1, slave1-2 auf HDMI-A-2)
- Assets werden on-demand vom Head-Pi gecacht
- Playlists persistent gespeichert (ueberlebt Neustart ohne Head-Pi)
- Desktop (lightdm) deaktiviert — reines CLI + DRM
- apt-Timer deaktiviert
- avoid_warnings=2
- USB-Auto-Mount vorbereitet (/media/displaywall)
- SSH: `ssh slave1-pi` (User: slave1, Key: id_ed25519_pi)
- Ethernet: 192.168.192.157, WLAN: 192.168.192.65

## Aktueller Zustand Head-Pi (2026-04-12)

- Anthias laeuft (7 Docker-Container), Assets rotieren auf HDMI-A-1
- **Dual-Display aktiv:** Viewer-2 (systemd) bespielt HDMI-A-2 via `mpv --vo=gpu --gpu-context=drm`
- Aufloesung: 2560x1440 auf beiden HDMI-Ausgaengen (via `video=` in cmdline.txt)
- `avoid_warnings=2` gesetzt
- `wlr-randr` und `kanshi` installiert
- CPU-Pinning: Anthias auf Kerne 0-1, Viewer-2 auf Kerne 2-3
- **VJ-Manager GUI** auf Port 8080 (PocketVJ-inspiriert, Dark Theme)
  - Canvas-Editor (Fabric.js 5.3.0, lokal): Monitore anordnen, Playlists verwalten
  - Pool-Sidebar: Assets hochladen, per Drag&Drop zuweisen
  - Preview-Tooltips: Mouseover zeigt Bild/Video-Vorschau
  - Live-Preview-Panel: Zeigt aktuelles Asset in Echtzeit neben der Playlist
  - Playback-Highlight: Aktuell spielendes Asset markiert (clientseitiger Timer-Tracker)
  - Transport-Toolbar: Previous/Play/Pause/Stop/Next mit Farb-Feedback (gruen/rot/orange)
  - Canvas-Resize: CSS resize:both im Anordnen-Modus, 70% Breite im Auswaehlen-Modus
  - Devices-Tab: Pi-Karten mit Status, Rotation, Netzwerk-Infos
  - Shuffle-Modus: Toggle pro Monitor (wie CD-Player)
  - Alle Dependencies lokal (kein Internet noetig)
- Testsuite (`displaywall-test.sh`) verfuegbar und funktionsfaehig
- Kein USB-Speicher gemountet (nur 58GB SD-Karte)
- SSH-Zugriff von WSL2 funktioniert (Key-basiert, `ssh head-pi`)

## Architektur-Entscheidungen (2026-04-10)

### Warum kein PiSignage-Pivot?

Statt PiSignage (Option C aus PLAYER_EVALUATION.md) wurde Anthias beibehalten und um einen
eigenstaendigen Viewer-2 ergaenzt. Gruende:
- Anthias laeuft bereits stabil auf dem Head-Pi
- PiSignage haette eine komplette Neuinstallation bedeutet
- Die Dual-Display-Loesung mit Viewer-2 funktioniert ohne Lizenzkosten
- mpv mit `--vo=gpu --gpu-context=drm` kann den zweiten HDMI-Ausgang nutzen, ohne den DRM-Master-Lock von Anthias zu stoeren

### DRM-Master-Problem (geloest)

`mpv --vo=drm` braucht exklusiven DRM-Master-Zugriff. Anthias (ScreenlyWebview mit linuxfb) haelt diesen Lock auf `/dev/dri/card1`. Loesung: Viewer-2 nutzt `--vo=gpu --gpu-context=drm` (EGL/DRM), das keinen exklusiven Lock braucht. Voraussetzung: User `head` muss in der Gruppe `render` sein.

## VJ-Manager v2.0 (ab 2026-04-11)

Siehe `FSD_VJ_MANAGER.md` fuer die vollstaendige Spezifikation.

### Evaluierungen

- **PocketVJ:** Evaluiert und verworfen. Basiert auf omxplayer (deprecated, nicht Pi-5-kompatibel), Projekt seit 2021 inaktiv. Sync-Algorithmus (omxplayer-sync) wird als Referenz fuer die eigene Implementierung genutzt.
- **VPT 8 (VideoProjectionTool):** Verworfen. Keine ARM64/Linux-Unterstuetzung (Max/MSP-basiert).
- **Google Chicago Brick:** Verworfen. Nicht mehr gepflegt, Browser-Rendering auf Pi 5 zu instabil.

### Waypoints

- [x] **WP1:** wall_config.json Schema + Backend (REST-API) — abgeschlossen 2026-04-11
- [x] **WP2:** Canvas-GUI mit Fabric.js (Pool + Canvas + Playlists) — abgeschlossen 2026-04-12
- [ ] **WP3:** Masterclock Sync-Layer (NTP + UDP + mpv IPC, portiert von omxplayer-sync)
- [ ] **WP4:** WLAN-Latenz-Validierung unter Last
- [ ] **WP5:** HDMI-Capture-Streaming (ffmpeg/kmsgrab → Live-Thumbnails in GUI)

### Weitere TODOs

- [x] USB-Auto-Mount vorbereitet (udev-Regel + Mount-Skript, `/media/displaywall`)
- [x] Slave-Setup-Skript geschrieben (`setup-slave.sh`)
- [x] Slave-Agent geschrieben (`displaywall-agent.py` — REST-API, 2x mpv, Asset-Cache)
- [x] Slave1 eingerichtet und getestet (Agent laeuft, Assets cached, Playlists persistent)
- [ ] Slave2 einrichten (gleicher Prozess wie Slave1)
- [ ] Netzteil-Spannung an allen 3 Pis pruefen (`monitor-power.sh`)
- [ ] SSH-Keys auf alle Pis verteilen

## Hinweise für KI-Agenten
- **Sprache:** Die Endnutzer-Dokumentation soll auf **Deutsch** verfasst sein.
- **Zielgruppe:** Der Nutzer führt manuelle Schritte am echten Raspberry Pi durch.
- **Hardware-Limitierung:** Bedenke bei Änderungen, dass das System auf Raspberry Pi 5 (ARM64) Architektur läuft.
- **Credentials:** Zugangsdaten (User, Passwort, WLAN) werden bewusst offen in der Doku gefuehrt. Das sind Installations-Defaults wie bei Consumer-Hardware.
- **Display-Regel:** Im Betrieb duerfen KEINE Warnungen, Overlays oder Desktop-Elemente auf den Bildschirmen erscheinen. Systemwarnungen gehen per Monitoring an den Admin, nie auf die Displays.
- **Sync:** Display-Synchronisation wird ueber eigenen Sync-Layer realisiert (adaptiert von omxplayer-sync, portiert auf mpv IPC). Siehe `FSD_VJ_MANAGER.md`.
- **PocketVJ:** Nicht verwenden — basiert auf omxplayer, laeuft nicht auf Pi 5.
