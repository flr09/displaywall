# AI Handover & Project Status: Displaywall

## Projektübersicht
Dieses Projekt umfasst die Planung, Hardware-Zusammenstellung und Software-Konfiguration für eine Videowall, bestehend aus 6 WQHD-Monitoren (2560x1440), die von 3 Raspberry Pi 5 Systemen angesteuert werden. 

Die Wand ist gemischt ausgerichtet:
- 4 Monitore im Querformat (Landscape)
- 2 Monitore im Hochformat (Portrait)

Die zentrale Steuerung erfolgt über **Xibo CMS**, welches auf einem der 3 Raspberry Pis (dem "Head-Pi") via Docker gehostet wird. Alle Pis nutzen den **Xibo Linux Player** (Snap).

## Bisherige Meilensteine (Stand: heute)
- [x] Projekt-Spezifikation (`README.md`) mit Hardware- und Software-Requirements erstellt.
- [x] Ordnerstruktur (`software/`) aufgebaut.
- [x] Die aktuelle Xibo CMS Version (4.4.1) via Docker-Compose als `.tar.gz` heruntergeladen und entpackt.
- [x] Ein automatisiertes Bash-Installationsskript (`software/setup.sh`) für Docker, Docker-Compose und den Xibo-Player geschrieben.
- [x] Schritt-für-Schritt-Anleitung (`HOWTO_INSTALL.md`) für den Endnutzer verfasst, die den Prozess vom SD-Karte Flashen (mit Balena Etcher) bis zur CMS-Konfiguration für den Head-Pi erklärt.
- [x] Git-Repository initialisiert und `.gitignore` konfiguriert (schließt große Archivdateien aus).
- [x] Headless-Anleitung (`HOWTO_CLIENTS.md`) und Setup-Skript (`setup-client.sh`) für die Client-Pis erstellt.

## Dateistruktur & Zweck
- `README.md` -> Das generelle Konzept, Hardware-Listen, Netzwerk-Layout.
- `HOWTO_INSTALL.md` -> Detailanleitung (Step-by-Step) für den menschlichen Administrator zur Einrichtung des Head-Pis.
- `HOWTO_CLIENTS.md` -> Headless-Installationsanleitung via Raspberry Pi Imager und SSH für die beiden Client-Pis.
- `STATUS.md` -> Dieses Dokument. Es dient als Kontext und Übergabedokument für zukünftige KI-Sitzungen.
- `software/` -> Enthält alle Downloads, Installations-Skripte und Docker-Konfigurationen, die offline auf die Pis übertragen werden.
  - `setup.sh` -> Shell-Skript zur Installation von Docker und Snap (Xibo-Player) auf dem Head-Pi.
  - `setup-client.sh` -> Shell-Skript für die Headless-Installation des Xibo-Players auf den Client-Pis.
  - `xibo-docker-*/` -> Die ausgepackten Docker-Dateien für das Xibo CMS (wird auf dem Head-Pi in `docker compose up -d` ausgeführt).

## Nächste Schritte (TODOs)
- [ ] Klärung von Netzwerkeinstellungen (DHCP vs. statische IP), damit die Client-Pis den Head-Pi zuverlässig finden.
- [ ] Automatisierung des Display-Layouts (xrandr oder Wayland-Konfiguration) für die Quer- und Hochformate.
- [ ] Erstellung der Xibo-Layouts für die jeweilige Bildschirmauflösung.

## Hinweise für KI-Agenten
- **Sprache:** Die Endnutzer-Dokumentation (README, HOWTO) soll auf **Deutsch** verfasst sein, da der User dies so initiiert hat.
- **Zielgruppe:** Der Nutzer führt manuelle Schritte am echten Raspberry Pi durch (z.B. SD-Karten flashen, Kabel stecken). Erklärungen müssen praktisch anwendbar und fehlerverzeihend formuliert sein.
- **Hardware-Limitierung:** Bedenke bei Änderungen, dass das System auf Raspberry Pi 5 (ARM64) Architektur läuft. Docker-Images und Software-Pakete müssen damit kompatibel sein.
- Wenn neue Software-Pakete benötigt werden, lade sie idealerweise direkt als Offline-Installationspaket herunter oder ergänze das `setup.sh`-Skript, da die Pis während der Installation evtl. am endgültigen Standort eine eingeschränkte Internetverbindung haben.
