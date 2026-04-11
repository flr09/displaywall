# FSD: Displaywall VJ-Manager (v2.0)

## 1. Funktionale Komponenten

### A. Der Canvas (Bühne)
- Visuelle Repräsentation der 6 Monitore als Rechtecke.
- Interaktives Mapping: Jedes Rechteck speichert seine Koordinaten (X, Y) und Rotation (0, 90).
- Hardware-Mapping: Verknüpfung "Kasten" zu "Hardware-Output" (z.B. Slave-1, HDMI-2).

### B. Die Playlist (Aktiver Slot)
- Kontextsensitiv: Zeigt den Inhalt des im Canvas gewählten Monitors.
- Funktionen: Sortieren, Löschen, Zeit-Offset (+/- Sek.).
- Trigger: Sobald ein Asset in die Liste gezogen wird, startet der Pre-Load auf dem Ziel-Pi.

### C. Der Pool (Lager)
- Persistente Speicherung der Assets auf dem Head-Pi.
- Mehrfachzuweisung: Ein Asset kann gleichzeitig auf mehreren Monitoren liegen.

## 2. Technische Realisierung der Synchronisation

Die **Masterclock** wird über eine zentrale WebSocket-Instanz auf dem Head-Pi realisiert:
1. Der Head-Pi emittiert einen `TICK` mit der aktuellen Systemzeit und dem `ActiveAssetIndex`.
2. Alle Viewer-Instanzen (lokal und auf Slaves) berechnen ihren individuellen `TargetFrame`:
   `Target = MasterTick - Offset(Local)`
3. Bei Abweichungen > 100ms springt der Player (mpv) zum Zielframe (Hard-Sync).

## 3. Datenstruktur (wall_config.json)
```json
{
  "canvas": {
    "monitors": [
      {"id": 1, "x": 100, "y": 100, "rot": 0, "output": "head:hdmi1", "offset": 0},
      {"id": 2, "x": 2660, "y": 100, "rot": 90, "output": "head:hdmi2", "offset": 5.0}
    ]
  },
  "assets": [
    {"name": "intro.mp4", "type": "video", "assigned_to": [1, 2]}
  ]
}
```
