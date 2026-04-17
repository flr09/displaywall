# Displaywall — Installationsanleitung

Komplette Anleitung zum Aufbau einer synchronisierten Displaywall
mit Raspberry Pi 5. Jeder Pi steuert 2 HDMI-Monitore, alle Displays
wechseln sekundengenau synchron (~17ms Versatz).

---

## Architektur

```
┌─────────────────────────────────────────────────────┐
│               TP-Link Router (AP)                   │
│      SSID: displaywall  /  Pass: 12345678           │
│                 10.42.0.1/24                         │
│    ┌──────────┬──────────┬──────────┐               │
│    │          │          │          │                │
│  Head-Pi   Slave1     Slave2    Slave-N ...         │
│ 10.42.0.1  10.42.0.22 10.42.0.23 10.42.0.2x        │
│  Port 8080  Port 8081  Port 8081  Port 8081         │
│  2x HDMI    2x HDMI    2x HDMI    2x HDMI           │
└─────────────────────────────────────────────────────┘
```

**Head-Pi:** Web-GUI (Port 8080), Sync-Master (UDP 1666), Viewer (2x mpv)
**Slave-Pi:** Agent (Port 8081), Sync-Slave (UDP 1666), Viewer (2x mpv)

## Hardware

| Komponente | Stueck | Bemerkung |
|---|---|---|
| Raspberry Pi 5 (4GB+) | 1 + N Slaves | 8GB empfohlen ab >4 Slaves |
| USB-C Netzteil 27W | 1 pro Pi | Offizielles Pi 5 Netzteil |
| microSD 32GB+ | 1 pro Pi | Class A2 empfohlen |
| Micro-HDMI → HDMI Kabel | 2 pro Pi | Beide Ports nutzbar |
| HDMI-Monitor | 2 pro Pi | Max 2560x1440 (GPU-Limit) |
| TP-Link WLAN-Router | 1 | Als dedizierter AP fuer das displaywall-Netz |
| Ethernet-Kabel | 1 | Nur fuer Ersteinrichtung (temporaer) |

### Optionaler USB-WiFi-Adapter (nur Head)

Wenn der Head-Pi den Hotspot SELBST bereitstellen soll (ohne TP-Link
Router), braucht er einen zweiten WiFi-Adapter. Der interne ist dann
fuer den Hotspot belegt, der USB-Adapter fuer Internet-Uplink.

Empfohlen: TP-Link TL-WN725N (rtl8188eu, arm64-kompatibel).

Mit dediziertem TP-Link Router ist kein USB-Adapter noetig.

## Skalierung

| Monitore | Pis | Bewertung |
|---|---|---|
| 2-4 | 1-2 | Trivial, Head allein oder +1 Slave |
| 6-12 | 3-6 | Optimaler Bereich, WLAN stabil |
| 14-20 | 7-10 | Funktioniert gut mit gutem Router |
| 22-30 | 11-15 | Router muss 15+ Clients verkraften |
| 32-50 | 16-25 | Ethernet-Switch empfohlen statt WLAN |
| 50+ | 25+ | Moeglich, aber: Ethernet Pflicht, evtl. mehrere Sync-Segmente |

**Theoretisches Limit:** Das Sync-Protokoll (UDP-Broadcast, 1 Paket/s)
skaliert bis ~100 Slaves. Die Playlist-Berechnung ist deterministisch
(keine Kommunikation noetig). Praktisches Limit ist das Netzwerk:
WiFi-Router schaffen typisch 15-20 Clients stabil.

Ab ~50 Monitoren sollte man ueber Ethernet + managed Switch nachdenken.
Ab ~100 Monitoren waere ein dedizierter Sync-Server (statt Pi) sinnvoll.

## Betriebssystem

**Exakt diese Version verwenden:**

- **OS:** Raspberry Pi OS (64-bit), Debian 13 "trixie"
- **Kernel:** 6.6.x
- **Release:** 2026-Q1 oder neuer

**Wichtig:** Alle Pis muessen dieselbe OS-Version haben. Mismatch
zwischen Bookworm/Trixie fuehrt zu Inkompatibilitaeten bei labwc, mpv
und Python-Versionen.

## Netzwerk-Plan

| Geraet | IP | Funktion |
|---|---|---|
| TP-Link Router | 10.42.0.1 | DHCP-Server + AP |
| Head-Pi | 10.42.0.10 | VJ-Manager + Viewer + Sync-Master |
| Slave 1 | 10.42.0.22 | Agent + Viewer |
| Slave 2 | 10.42.0.23 | Agent + Viewer |
| Slave N | 10.42.0.(21+N) | Agent + Viewer |

**WLAN:** SSID `displaywall`, Passwort `12345678`, Kanal 6, WPA2-PSK
**SSH-User:** Hostname als Username (z.B. `head`/`slave1`), Passwort `12345678`

## Zugangsdaten (Uebersicht)

| Was | Wert |
|---|---|
| WLAN SSID | `displaywall` |
| WLAN Passwort | `12345678` |
| SSH User (Head) | `head` |
| SSH User (Slave) | `slave1`, `slave2`, ... |
| SSH Passwort | `12345678` |
| Web-GUI | `http://10.42.0.10:8080` |
| Slave-API | `http://10.42.0.2x:8081/api/status` |
| Admin-AP (Failover) | SSID=Hostname, Pass=`12345678`, IP=`192.168.50.1` |

---

## TP-Link Router einrichten

1. Router mit Strom verbinden, per Ethernet oder Standard-WLAN verbinden
2. Webinterface oeffnen (meist `192.168.0.1` oder `tplinkwifi.net`)
3. Einstellungen:
   - **SSID:** `displaywall`
   - **Passwort:** `12345678`
   - **Sicherheit:** WPA2-PSK
   - **Kanal:** 6 (fest, kein Auto)
   - **LAN-IP:** `10.42.0.1`
   - **Subnetz:** `255.255.255.0`
   - **DHCP:** Aktiviert, Bereich `10.42.0.100 - 10.42.0.200`
     (die Pis nutzen statische IPs ausserhalb dieses Bereichs)
4. Aenderungen speichern, Router neu starten

---

## Installation

### Variante A: Automatisch (empfohlen)

Die Installations-Scripts machen alles ausser SD-Karte flashen:

```bash
# 1. SD-Karte flashen (Pi Imager)
#    → siehe "SD-Karte flashen" unten

# 2. Head-Pi einrichten
scp install-head.sh head-pi:
ssh head-pi "chmod +x install-head.sh && sudo ./install-head.sh"

# 3. Slave einrichten (pro Slave wiederholen)
scp install-slave.sh slave1-pi:
ssh slave1-pi "chmod +x install-slave.sh && sudo ./install-slave.sh"
```

### Variante B: Manuell

Siehe die detaillierten Schritte in `HOWTO_SLAVE_SETUP.md`.

---

## SD-Karte flashen (Pi Imager)

Fuer **jeden** Pi (Head + Slaves):

1. Raspberry Pi Imager oeffnen
2. **OS:** Raspberry Pi OS (64-bit), Release "trixie" (Debian 13)
3. **Zahnrad → Erweiterte Optionen:**
   - **Hostname:** `head` (bzw. `slave1`, `slave2`, ...)
   - **Username:** `head` (bzw. `slave1`, `slave2`, ...)
   - **Passwort:** `12345678`
   - **SSH:** Aktivieren (Passwort-Auth)
   - **WLAN:** `displaywall` / `12345678` (Land: DE)
   - **Locale:** Europe/Berlin, de
4. Auf SD-Karte schreiben, in Pi einlegen, booten (~2 min Firstboot)

---

## Nach der Installation

### Web-GUI

Browser oeffnen: `http://10.42.0.10:8080`

- **Assets hochladen:** Drag & Drop oder Dateiauswahl (Bilder werden
  automatisch auf max 2560x1440 skaliert)
- **Playlists zuweisen:** Assets per Drag & Drop auf Monitore ziehen
- **Steuerung:** Play/Pause/Next/Prev pro Monitor oder global
- Slaves empfangen Playlists automatisch (Pull alle 30s)

### Monitore hinzufuegen

1. Neuen Slave flashen + `install-slave.sh` ausfuehren
2. `slaves.json` auf dem Head erweitern:
   ```json
   {
     "slave1": {"ip": "10.42.0.22", "port": 8081},
     "slave2": {"ip": "10.42.0.23", "port": 8081},
     "slave3": {"ip": "10.42.0.24", "port": 8081}
   }
   ```
3. Head-Viewer neustarten: `pkill -f viewer.py` (startet automatisch neu)

### Admin-AP (Failover)

Wenn ein Slave das displaywall-WLAN 3 Minuten nicht findet, oeffnet er
einen eigenen AP:
- **SSID:** Hostname (z.B. `slave1`)
- **Passwort:** `12345678`
- **IP:** `192.168.50.1`

So kann man sich per Laptop verbinden und den Slave diagnostizieren,
auch wenn der Head-Pi oder Router ausgefallen ist. Sobald das
displaywall-WLAN wieder sichtbar wird, schliesst der Slave den AP
und verbindet sich automatisch zurueck.

---

## Troubleshooting

- **SSH Permission denied:** Firstboot laeuft noch, 1-2 min warten
- **Kein Bild auf Monitor:** `ssh <pi> "pgrep -af mpv"` — mpv laeuft?
- **Bilder nicht synchron:** `curl http://<slave>:8081/api/status` → `sync.has_master` muss `true` sein
- **Asset wird nicht angezeigt:** Bild evtl. >4096px → wird automatisch skaliert beim Upload
- **Slave nicht erreichbar:** Admin-AP pruefen (Laptop mit SSID=Hostname verbinden)
- **Cursor sichtbar:** `pkill labwc` auf dem Pi (startet automatisch neu)
