# AI Handover & Project Status: Displaywall

## Projektübersicht
Dieses Projekt umfasst die Planung, Hardware-Zusammenstellung und Software-Konfiguration für eine Videowall, bestehend aus 6 WQHD-Monitoren (2560x1440), die von 3 Raspberry Pi 5 Systemen angesteuert werden. 

Die Wand ist gemischt ausgerichtet:
- 4 Monitore im Querformat (Landscape)
- 2 Monitore im Hochformat (Portrait)

**WICHTIG:** Nach einem fehlgeschlagenen Architektur-Versuch mit Xibo CMS (der Xibo-Player ist nicht für die ARM64-Architektur des Pi 5 verfügbar), wurde das Projekt auf **Anthias (Screenly OSE)** umgestellt. Es gibt nun keine Master/Slave-Architektur mehr, sondern 3 identische, autarke Pis mit eigenem Web-Dashboard.

## Bisherige Meilensteine (Stand: heute)
- [x] Projekt-Spezifikation (`README.md`) aktualisiert.
- [x] Skript und Anleitung (`HOWTO_ROTATION.md`) für die Drehung der Monitore in Wayland (Hochformat) erstellt.
- [x] Umstieg auf offizielles Raspberry Pi OS (Debian) (64-bit).
- [x] Recherche und Dokumentation (`SYNC_OPTIONS.md`) zu Frame-genauer Synchronisation der Pi-Cluster.
- [x] **PIVOT:** Veraltete Xibo-Skripte und Docker-Files gelöscht.
- [x] **PIVOT:** Neues Installations-Skript (`setup-anthias.sh`) geschrieben.
- [x] **PIVOT:** Neue, stark vereinfachte Anleitung (`HOWTO_ANTHIAS.md`) verfasst.

## Dateistruktur & Zweck
- `README.md` -> Das generelle Konzept, Hardware-Listen.
- `HOWTO_ANTHIAS.md` -> Anleitung (Step-by-Step) für die identische Einrichtung aller 3 Pis mit dem Raspberry Pi Imager und dem neuen Skript.
- `HOWTO_ROTATION.md` -> Anleitung zum Drehen der Monitore via SSH (Live-Test und dauerhafter Autostart).
- `SYNC_OPTIONS.md` -> Analyse der Synchronisations-Herausforderungen (Hardware vs. Software) auf dem Pi 5.
- `STATUS.md` -> Dieses Dokument.
- `sd-card-config/` -> Manuelle Fallback-Dateien für Headless-Boot (falls der Pi-Imager zickt).
- `software/` -> Enthält alle Skripte, die offline auf die Pis übertragen werden.
  - `setup-anthias.sh` -> Wrapper-Skript, das das offizielle Anthias-Setup startet.
  - `rotate-screen.sh` -> Helfer-Skript zum direkten Drehen der Monitore via Wayland (`wlr-randr`).

## Nächste Schritte (TODOs)
- [ ] Upload der finalen MP4-Videos (Drittel-Splits) über die Anthias-Dashboards.
- [ ] Erstellung der dauerhaften `wayfire.ini` Rotations-Regeln für die Hochformat-Pis.

## Hinweise für KI-Agenten
- **Sprache:** Die Endnutzer-Dokumentation soll auf **Deutsch** verfasst sein.
- **Zielgruppe:** Der Nutzer führt manuelle Schritte am echten Raspberry Pi durch.
- **Hardware-Limitierung:** Bedenke bei Änderungen, dass das System auf Raspberry Pi 5 (ARM64) Architektur läuft.
