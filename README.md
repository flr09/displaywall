# Projekt-Spezifikation: Monitorwall

6 Monitore / 3 Raspberry Pi 5

## 1. Konzept

Auf 6 Monitoren (Hochkant und Querformat gemischt) werden Medieninhalte (Videos, Bilder) dargestellt. Die Verwaltung erfolgt zentral ueber einen **Head-Pi**, der die Inhalte auf die einzelnen Displays verteilt und zuordnet.

### Kernfunktionen

- **Zentrale Verwaltung:** Der Head-Pi steuert, welche Medien auf welchem Display laufen.
- **Medien-Zuordnung:** Inhalte werden einzelnen Displays oder Display-Gruppen zugewiesen.
- **Externer Speicher:** Medien werden von einer USB-Festplatte oder einem USB-Stick gehostet (SD-Karten sind zu klein fuer groessere Videodateien).
- **Gruppen (optional):** Falls moeglich, sollen Displays in Gruppen zusammengefasst werden koennen, die Medien untereinander tauschen.
- **Display-Synchronisation (optional):** Frame-genauer Sync ueber mehrere Displays ist wuenschenswert, aber nicht zwingend erforderlich.

### Regeln fuer den Betrieb

- **Keine Warnungen auf den Displays.** Im Betrieb darf auf keinem Bildschirm eine Systemwarnung, ein Desktop-Element oder ein Overlay erscheinen. Warnungen (Undervoltage, Updates, etc.) werden per Monitoring an den Admin weitergeleitet, aber nie auf den Bildschirmen angezeigt.
- **Kiosk-Modus:** Alle Displays laufen im randlosen Vollbild. Kein Desktop, keine Taskbar, keine Mauszeiger.
- **Auto-Recovery:** Nach Stromausfall booten die Pis automatisch und starten die Wiedergabe ohne manuellen Eingriff.

## 2. Hardware-Setup

* **Rechner:** 3x Raspberry Pi 5 (4GB RAM).
* **Gehaeuse:** Waveshare Pi5-Module-BOX (Stromanschluss rueckseitig).
* **Displays:** 6x Monitore mit WQHD-Aufloesung (2560 x 1440 Pixel).
* **Konfiguration:** Jeweils 2 Monitore pro Pi.
* **Ausrichtung:** 4 Monitore im Querformat, 2 Monitore im Hochkantformat (Portrait).
* **Speicher:** USB-Festplatte oder USB-Stick am Head-Pi fuer Mediendateien.
* **Netzwerk:** WLAN ueber interne Antenne oder USB-WLAN-Adapter mit externer Antenne.

## 3. Software-Stack (Kostenfrei / Open Source)

* **Betriebssystem:** Raspberry Pi OS (Bookworm, 64-bit), Wayland (Wayfire).
* **Player & Management:** [Anthias (Screenly OSE)](https://anthias.srly.io/).
* **Monitoring:** `monitor-power.sh` fuer Spannungs- und Throttle-Ueberwachung per SSH/CSV.

## 4. Stromversorgung

Die Waveshare-Gehaeuse leiten Strom ueber einen MOSFET (kein USB-PD) an den Pi durch. Standard-5V-Netzteile reichen nicht aus. Details und Loesungen siehe `HOWTO_ANTHIAS.md` (Abschnitt Stromversorgung).

## 5. Zugangsdaten

| Was | Wert |
|-----|------|
| **Benutzer** | **`Head`** |
| **Passwort** | **`12345678`** |
| **WLAN** | SSID: **`DisplayWall-Netzwerk`**, Passwort: **`DisplayPassword123`** |

*Koennen nach der Einrichtung jederzeit geaendert werden.*

## 6. Links & Ressourcen

* **OS Download:** Ueber den [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
* **Anthias Projekt:** [Github Anthias](https://github.com/Screenly/Anthias)
* **Installation:** Siehe `HOWTO_ANTHIAS.md`
