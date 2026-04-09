# Projekt-Spezifikation: Monitorwall

6 Monitore / 3 Raspberry Pi 5

## 1. Hardware-Setup

* **Rechner:** 3x Raspberry Pi 5 (4GB RAM Variante).
* **Displays:** 6x Monitore mit WQHD-Auflösung (2560 × 1440 Pixel).
* **Konfiguration:** Jeweils 2 Monitore pro Pi WQHD-Video.
* **Besonderheit:** 4 Monitore im Querformat, 2 Monitore im Hochkantformat (Portrait).
* **Netzwerk:** WLAN über interne Antenne oder USB-WLAN-Adapter mit externer Antenne (falls Abschirmung durch Monitore zu hoch).

## 2. Software-Stack (Kostenfrei / Open Source)

*   **Betriebssystem:** Raspberry Pi OS (Bookworm, 64-bit).
    *   *Einstellung:* Wayland (Wayfire) bleibt aktiv für volle Kompatibilität mit dem Raspberry Pi 5.
*   **Player & Management:** [Anthias (Screenly OSE)](https://anthias.srly.io/) (Open Source Digital Signage).
    *   Läuft identisch auf allen drei Pis. Es gibt keinen zentralen Master-Server.
    *   *Vorteil:* Jeder Pi hat eine eigene Web-Oberfläche. Videos werden direkt auf den jeweiligen Pi hochgeladen und abgespielt.
*   **Infrastruktur:** Nativ auf dem Pi installiert, ohne zusätzliche Docker-Komplexität.

## 3. Konfiguration der Anzeige (Kiosk-Mode)

*   **Rotation:** Die Ausrichtung (quer/hochkant) wird per SSH (über das Helfer-Skript `wlr-randr`) eingestellt und für den Autostart dauerhaft in die `wayfire.ini` geschrieben.
*   **Layout:** Die großen 4K/6K Wand-Videos werden am PC vorab in 3 separate Dateien gerendert und dann auf die jeweiligen Pis hochgeladen.
*   **Video-Codec:** Um die Hardware-Beschleunigung des Pi 5 optimal zu nutzen, sollten alle Videos im H.265 (HEVC) oder H.264 Format vorliegen.

## 4. Workflow für den Betrieb

1.  **Verwaltung:** Jeder Pi wird über seine eigene lokale IP-Adresse (z.B. `http://pi-links.local`) im Webbrowser aufgerufen.
2.  **Inhalts-Update:** Im Dashboard des Pis auf "Add Asset" klicken -> Video hochladen -> Als "Active" markieren.
3.  **Wiedergabe:** Anthias bootet automatisch in den randlosen Vollbildmodus (Kiosk) und spielt die hochgeladenen Videos im Endlos-Loop ab.

## 5. Links & Ressourcen

*   **OS Download:** Über den [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
*   **Anthias Projekt:** [Github Anthias](https://github.com/Screenly/Anthias)
*   **Installation:** Wird automatisiert über das mitgelieferte `setup-anthias.sh` Skript ausgeführt.
