# Displaywall — Projektstatus

Stand: 2026-04-17

## Aktueller Zustand

Das System laeuft produktiv mit 3 Raspberry Pi 5 und 6 Monitoren (2x HDMI pro Pi).

### Architektur

- **OS:** Raspberry Pi OS (64-bit), Debian 13 "trixie", labwc (Wayland)
- **Player:** mpv persistent mit IPC (`--gpu-context=wayland`, `--background=none`)
- **Head-Pi:** viewer.py (Sync-Master) + displaywall-mgr.py (Web-GUI, Port 8080)
- **Slave-Pis:** displaywall-agent.py (Sync-Slave, REST-API, Port 8081)
- **Sync:** CLOCK_MONOTONIC_RAW + UDP-PLL (Port 1666), ~17ms Versatz
- **Pre-Decode:** Bilder 3s vor Wechsel vorgeladen (`loadfile append` + `playlist-next`)
- **Netzwerk:** TP-Link Router als AP (SSID `displaywall`, 10.42.0.0/24)

### Pis

| Pi | IP | Rolle | Monitore | Status |
|---|---|---|---|---|
| head | 10.42.0.10 | Master | head-1, head-2 | Laeuft stabil |
| slave1 | 10.42.0.22 | Slave | slave1-1, slave1-2 | Laeuft stabil, Sync aktiv |
| slave2 | 10.42.0.23 | Slave | slave2-1, slave2-2 | Laeuft, HDMI-2 ohne Monitor |

### Erledigte Features

- [x] Web-GUI mit Canvas-Editor, Asset-Pool, Drag & Drop
- [x] Playlists pro Monitor (Bilder + Videos, konfigurierbare Duration)
- [x] Transport-Controls (Play/Pause/Next/Prev) pro Monitor
- [x] Shuffle-Modus pro Monitor
- [x] Playback-Highlight (aktuelles Asset in Playlist markiert)
- [x] Live-Preview und Thumbnails
- [x] Devices-Tab (Temperatur, Speicher, Netzwerk, Throttle)
- [x] Cross-Pi Sync (TickClock + DeterministicPlaylist + SyncMaster/Slave)
- [x] Pre-Decode (loadfile append + playlist-next)
- [x] Asset-Validierung (defekte Assets werden uebersprungen, GUI-Markierung)
- [x] Auto-Resize beim Upload (max 2560x1440, GPU-Texturlimit)
- [x] Persistenter mpv (kein Flackern beim Bildwechsel)
- [x] Slave-Agent mit Pull-Loop (30s) + lokaler Playlist-Cache
- [x] Admin-AP Failover (Slave wird AP wenn displaywall-WLAN weg)
- [x] Unsichtbarer Cursor (labwc + Xcursor-Theme)
- [x] Auto-Recovery nach Stromausfall
- [x] Watchdog (ueberwacht Services, Temperatur, Netzwerk)
- [x] Automatische Installations-Scripts (install-head.sh, install-slave.sh)

### Offene Punkte

- [ ] Systemzeit auf slave2 falsch (Apr 13 statt Apr 17) — NTP einrichten
- [ ] SCHED_FIFO braucht Root-Rechte — CAP_SYS_NICE oder chrt in autostart
- [ ] HDMI-Capture-Streaming (Live-Thumbnails in GUI)
- [ ] Videos in Playlists testen (bisher nur Bilder verifiziert)
- [ ] USB-Speicher als Asset-Storage (vorbereitet, nicht getestet)

## Architektur-Historie

1. **Xibo CMS** (2025-04) — Verworfen: ARM64-Player nicht verfuegbar.
2. **Anthias (Screenly OSE)** (2025-04) — Installiert, nur 1 Display pro Pi.
3. **Eigener Stack** (2026-04-10) — Pivot: labwc + mpv + eigener Sync-Layer.
   Anthias-DB wird noch fuer Asset-Metadaten referenziert.

Details zu verworfenen Ansaetzen: siehe `_historical/PLAYER_EVALUATION.md`.

## Hinweise fuer KI-Agenten

- **Sprache:** Dokumentation Deutsch, Code Englisch
- **Zielplattform:** Raspberry Pi 5 (arm64, Debian 13 trixie)
- **Display-Regel:** Keine Warnungen/Overlays auf Bildschirmen
- **Credentials:** Offen dokumentiert (Consumer-Hardware-Ansatz)
- **Sync:** Eigener Layer, NICHT omxplayer-sync oder NTP-basiert
- **Anthias:** Wird NICHT mehr als Player verwendet, nur DB fuer Assets
