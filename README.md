# Projekt-Spezifikation: Monitorwall

6 Monitore / 3 Raspberry Pi 5

## 1\. Hardware-Setup

* **Rechner:** 3x Raspberry Pi 5 (4GB RAM Variante).
* **Displays:** 6x Monitore mit WQHD-Auflösung (2560 × 1440 Pixel).
* **Konfiguration:** Jeweils 2 Monitore pro Pi  WQHD-Video.
* **Besonderheit:** 4 Monitore im Querformat, 2 Monitore im Hochkantformat (Portrait).
* **Netzwerk:** WLAN über interne Antenne oder USB-WLAN-Adapter mit externer Antenne (falls Abschirmung durch Monitore zu hoch).

## 2\. Software-Stack (Kostenfrei / Open Source)

* **Betriebssystem:** Ubuntu Desktop 24.04 LTS (64-bit).

  * *Einstellung:* Auto-Login aktiviert, Grafik-Session bei Bedarf auf "X11/Xorg" umstellen für bessere Hardware-Beschleunigung.
* **Zentrales Management (CMS):** [Xibo CMS](https://xibosignage.com/xibo/cms) (Self-Hosted via Docker).

  * Läuft auf einem der drei Pis als "Master" oder auf einem separaten Server im lokalen Netzwerk.
  * *Vorteil:* Zentrales Hochladen von Files, keine Abo-Kosten, Zeitsteuerung möglich.
* **Player-Software:** Xibo Linux Player (installiert via Snap).

  * Läuft auf allen drei Pis und zieht sich die Inhalte automatisch vom Master-Pi.
* **Infrastruktur:** Docker \& Docker-Compose (kostenlose Engine-Version für Linux).

## 3\. Konfiguration der Anzeige (Kiosk-Mode)

* **Rotation:** Die Ausrichtung (quer/hochkant) wird direkt im Betriebssystem (Ubuntu Display Settings) hinterlegt.
* **Xibo-Profile:** Im CMS werden spezifische Profile für "Quer" (2560 × 1440) und "Hochkant" (1440 × 2560) angelegt und den jeweiligen Pis zugewiesen.
* **Video-Codec:** Um die Hardware-Beschleunigung des Pi 5 optimal zu nutzen, sollten alle Videos im H.265 (HEVC) Format vorliegen.

## 4\. Workflow für den Betrieb

1. **Master-Pi:** Hostet die Datenbank und die Weboberfläche (CMS).
2. **Verwaltung:** Zugriff erfolgt über den Webbrowser eines beliebigen Laptops im selben Netzwerk.
3. **Inhalts-Update:** Video hochladen -> In Playliste einfügen -> Speichern.
4. **Verteilung:** Die drei Pis laden das neue Video im Hintergrund herunter und starten die Wiedergabe lokal (offline-fähig).

## 5\. Links \& Ressourcen

* **OS Download:** [Ubuntu for Raspberry Pi](https://ubuntu.com/download/raspberry-pi)
* **Xibo CMS (Docker):** [GitHub Releases](https://github.com/xibosignage/xibo-cms/releases)
* **Player Installation:** `sudo snap install xibo-player`

