# Displaywall

Synchronisierte Videowall mit Raspberry Pi 5. Jeder Pi steuert 2 HDMI-Monitore,
alle Displays wechseln zeitgleich (~17ms Versatz via Hardware-Counter-Sync).

```
┌─────────────────────────────────────────────────────────────┐
│              TP-Link Router  ·  SSID: displaywall           │
│                       10.42.0.1/24                          │
│                                                             │
│    Head-Pi ─────────── Slave1 ─────────── Slave2 ── ...     │
│   10.42.0.10          10.42.0.22          10.42.0.23        │
│   Web-GUI :8080       Agent :8081         Agent :8081       │
│   ┌──────┬──────┐     ┌──────┬──────┐     ┌──────┬──────┐  │
│   │HDMI-1│HDMI-2│     │HDMI-1│HDMI-2│     │HDMI-1│HDMI-2│  │
│   └──────┴──────┘     └──────┴──────┘     └──────┴──────┘  │
│                                                             │
│   ◄──── UDP 1666: Tick-Sync (1 Hz, CLOCK_MONOTONIC_RAW) ──►│
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Zentrale Web-GUI** — Assets hochladen, Playlists zuweisen, Monitore anordnen
  (Canvas-Editor mit Drag & Drop, Dark Theme)
- **Synchronisation** — Hardware-Counter-basiert (CLOCK_MONOTONIC_RAW), Software-PLL,
  deterministische Playlist-Berechnung. Kein akkumulierender Drift.
- **Pre-Decode** — Bilder werden 3 Sekunden vor dem Wechsel in mpv vorgeladen.
  Beim Tick: `playlist-next` (Buffer-Swap, kein Decode-Delay).
- **Auto-Recovery** — Alle Dienste starten nach Stromausfall automatisch.
  Slaves speichern Playlists lokal und spielen auch ohne Head-Pi weiter.
- **Admin-AP Failover** — Slave oeffnet eigenen WLAN-AP wenn das Haupt-WLAN
  3 Minuten lang nicht erreichbar ist (SSID = Hostname, Pass = 12345678).
- **Asset-Skalierung** — Bilder werden beim Upload automatisch auf max 2560x1440
  skaliert (Pi 5 GPU-Limit: 4096x4096 Textur).
- **Kiosk-Modus** — Kein Desktop, kein Cursor, keine Systemwarnungen auf den Displays.

## Hardware

| Komponente | Stueck | Bemerkung |
|---|---|---|
| Raspberry Pi 5 (4GB+) | 1 Head + N Slaves | 8GB empfohlen ab >4 Slaves |
| USB-C Netzteil 27W | 1 pro Pi | Offizielles Pi 5 Netzteil |
| microSD 32GB+ | 1 pro Pi | Class A2 empfohlen |
| Micro-HDMI → HDMI Kabel | 2 pro Pi | |
| HDMI-Monitor (max 2560x1440) | 2 pro Pi | |
| TP-Link WLAN-Router | 1 | Dedizierter AP fuer displaywall-Netz |

Waveshare Pi5-Module-BOX: Leitet Strom ueber MOSFET (kein USB-PD).
Bei Standard-5V-Netzteilen zu wenig Spannung → Netzteil auf ~5.4V einstellen.

## Software-Stack

- **OS:** Raspberry Pi OS (64-bit), Debian 13 "trixie"
- **Compositor:** labwc (Wayland)
- **Player:** mpv (`--vo=gpu --gpu-context=wayland`, persistent mit IPC)
- **Backend:** Python 3.13, kein Docker, kein externer Player-Framework
- **Web-GUI:** Vanilla JS + Fabric.js (lokal, kein Internet noetig)

## Zugangsdaten

| Was | Wert |
|---|---|
| WLAN SSID | `displaywall` |
| WLAN Passwort | `12345678` |
| SSH User | `head` / `slave1` / `slave2` / ... |
| SSH Passwort | `12345678` |
| Web-GUI | `http://10.42.0.10:8080` |
| Admin-AP (Failover) | SSID = Hostname, IP = 192.168.50.1 |

## Installation

Siehe [`INSTALL.md`](INSTALL.md) fuer die vollstaendige Anleitung.

Kurzversion:
```bash
# SD-Karte flashen (Pi Imager, Debian 13 trixie, 64-bit)
# Head:
sudo ./install-head.sh
# Slave (pro Pi):
sudo ./install-slave.sh
```

## Skalierung

| Monitore | Pis | Netzwerk |
|---|---|---|
| 2–12 | 1–6 | WiFi (TP-Link Router) |
| 14–30 | 7–15 | WiFi (guter Router, 15+ Clients) |
| 32–50 | 16–25 | Ethernet-Switch empfohlen |
| 50+ | 25+ | Ethernet Pflicht |

Das Sync-Protokoll skaliert theoretisch bis ~100 Slaves (1 UDP-Paket/s,
deterministische Playlist ohne Netzwerk-Traffic).

## Sync-Mechanik

```
Head-Pi                              Slave-Pi
────────                             ─────────
TickClock(T0)                        SyncSlave (UDP :1666)
  │                                    │
  ├─ tick = floor(hw_now - T0)         ├─ empfaengt {v:"dw3", t0, m_now, tick}
  │                                    ├─ offset = m_now - rx_hw
  ├─ DeterministicPlaylist             ├─ PLL: avg(offsets, 8 samples)
  │   pos = (tick + offset) % cycle    ├─ local_tick = floor(hw_now + avg_off - t0)
  │   → Index aus Schedule             │
  ├─ Pre-Decode: loadfile append       ├─ DeterministicPlaylist (gleiche Berechnung)
  │   (3s vor Wechsel)                 ├─ Pre-Decode: loadfile append
  │                                    │
  ├─ Tick-Grenze → playlist-next       ├─ Tick-Grenze → playlist-next
  │   (instant, vorgeladen)            │   (instant, vorgeladen)
  │                                    │
  ├─ Busy-Wait letzte 20ms            ├─ Busy-Wait letzte 20ms
  │                                    │
  └─ SyncMaster.send_tick()           └─ PLL konvergiert nach ~3s
      (UDP broadcast, 1 Hz)
```

**Ergebnis:** Alle Displays wechseln bei derselben Tick-Nummer.
Gemessener Versatz: ~17ms (PLL-Genauigkeit + IPC-Latenz).

## Dateistruktur

```
displaywall/
├── README.md                    ← dieses Dokument
├── INSTALL.md                   ← vollstaendige Installationsanleitung
├── install-head.sh              ← automatisches Head-Setup
├── install-slave.sh             ← automatisches Slave-Setup
├── FSD_VJ_MANAGER.md            ← VJ-Manager Spezifikation
│
├── software/
│   ├── viewer.py                ← Head-Viewer (2x mpv, Sync-Master)
│   ├── displaywall-agent.py     ← Slave-Agent (2x mpv, Sync-Slave, REST-API)
│   ├── displaywall-mgr.py       ← Web-GUI Backend (Port 8080)
│   ├── displaywall-watchdog.py  ← Health-Monitor + Auto-Restart
│   ├── displaywall-failover.sh  ← Admin-AP Failover Script
│   ├── displaywall-failover.service
│   ├── displaywall-mgr.service
│   │
│   ├── displaywall/             ← Python-Paket
│   │   ├── sync.py              ← TickClock, DeterministicPlaylist, SyncMaster/Slave
│   │   ├── wall.py              ← Wall-Config (Playlists, Monitor-Zuordnung)
│   │   ├── config.py            ← Zentrale Konfiguration
│   │   ├── db.py                ← Asset-Datenbank
│   │   └── status.py            ← System-Status-Abfragen
│   │
│   ├── webui/                   ← VJ-Manager Frontend
│   │   ├── index.html
│   │   ├── app.js               ← Hauptlogik (Playlists, Transport, Devices)
│   │   ├── canvas.js            ← Canvas-Editor (Fabric.js)
│   │   ├── style.css
│   │   └── fabric.min.js        ← Fabric.js (lokal, kein CDN)
│   │
│   ├── slave-templates/         ← labwc/autostart/cursor Vorlagen
│   ├── HOWTO_SLAVE_SETUP.md     ← Manuelle Slave-Einrichtung (Schritt fuer Schritt)
│   └── HOWTO_ROTATION.md        ← Monitor-Rotation via labwc
│
├── sd-card-config/              ← Netzwerk-/User-Templates fuer Pi Imager
│
└── _historical/                 ← Archivierte Dokumente (nicht mehr aktuell)
    ├── HOWTO_ANTHIAS.md
    ├── HOWTO_ANTHIAS_CLIENTS.md
    ├── HOWTO_DUAL_DISPLAY.md
    └── PLAYER_EVALUATION.md
```

## Architektur-Historie

1. **Xibo CMS** (2025) — Verworfen: Player nicht fuer ARM64 verfuegbar.
2. **Anthias (Screenly OSE)** (2025) — Installiert, lauffaehig, aber nur 1 Display pro Pi.
3. **Eigener Stack** (2026-04) — Aktuell: labwc + mpv + eigener Viewer/Agent/Sync-Layer.
   Anthias-Datenbank wird noch fuer Asset-Metadaten referenziert.

## Lizenz

MIT
