# Dual-Display Einrichtung (Anthias + Viewer-2)

Stand: 2026-04-10

## Ueberblick

Jeder Raspberry Pi 5 steuert **zwei WQHD-Monitore** (2560x1440) an:

| Display | HDMI-Ausgang | Player | Steuerung |
|---------|-------------|--------|-----------|
| Display 1 | HDMI-A-1 | Anthias (Docker) | http://\<Pi-IP\>:80 |
| Display 2 | HDMI-A-2 | Viewer-2 (systemd) | http://\<Pi-IP\>:8080 |

**CPU-Aufteilung:** Anthias laeuft auf Kernen 0-1, Viewer-2 auf Kernen 2-3.

## Displaywall Manager (Web-GUI)

Erreichbar unter: **http://192.168.193.105:8080**

### Funktionen

- **Zwei-Spalten-Ansicht:** Links Display 1, rechts Display 2
- **Assets verschieben:** Button klicken um ein Asset dem anderen Display zuzuweisen
- **Rotation:** Dropdown pro Display (0°/90°/180°/270°)
- **Status:** Viewer-Status, Temperatur
- **Link zur Anthias-UI:** Fuer Asset-Upload und erweiterte Einstellungen

### Assets hochladen

1. Anthias-UI oeffnen: http://192.168.193.105:80
2. Asset hochladen (Bild oder Video)
3. Displaywall Manager oeffnen: http://192.168.193.105:8080
4. Asset per Button auf das gewuenschte Display schieben

### Wie die Zuweisung funktioniert

Assets werden intern ueber ein Namens-Prefix gesteuert:
- **Kein Prefix** → Display 1 (Anthias)
- **Prefix `2:`** → Display 2 (Viewer-2)

Die Web-GUI setzt dieses Prefix automatisch. In der Anthias-UI sieht man z.B. `2:Firmenlogo.png` — das bedeutet: dieses Asset spielt auf Display 2.

## Rotation

### Ueber die Web-GUI

1. Displaywall Manager oeffnen (Port 8080)
2. Rotation-Dropdown fuer das gewuenschte Display aendern
3. **Reboot noetig** fuer Kernel-Level-Rotation (Hinweis erscheint)

### Manuell (Kommandozeile)

Rotation in `/boot/firmware/cmdline.txt` anpassen:
```
video=HDMI-A-1:2560x1440@60 video=HDMI-A-2:2560x1440@60,rotate=90
```

Werte: `0` (Landscape), `90` (Portrait rechts), `180` (umgedreht), `270` (Portrait links)

Danach: `sudo reboot`

### Rotations-Config

Die Rotation wird in `/home/head/.screenly/displays.json` gespeichert:
```json
{
  "HDMI-A-1": {"rotation": 0, "resolution": "2560x1440"},
  "HDMI-A-2": {"rotation": 90, "resolution": "2560x1440"}
}
```

## Technische Details

### Viewer-2

- **Pfad:** `/home/head/screenly/viewer2.py`
- **Service:** `anthias-viewer2.service`
- **Rendering:** `mpv --vo=gpu --gpu-context=drm --drm-connector=HDMI-A-2`
- **Datenquelle:** Anthias SQLite-DB (`/home/head/.screenly/screenly.db`)
- **CPU-Kerne:** 2, 3 (via systemd CPUAffinity)

### Displaywall Manager

- **Pfad:** `/home/head/screenly/displaywall-mgr.py`
- **Service:** `displaywall-mgr.service`
- **Port:** 8080
- **Dependencies:** Keine (Python stdlib)

### Service-Verwaltung

```bash
# Status pruefen
sudo systemctl status anthias-viewer2
sudo systemctl status displaywall-mgr

# Neu starten
sudo systemctl restart anthias-viewer2
sudo systemctl restart displaywall-mgr

# Logs ansehen
journalctl -u anthias-viewer2 -f
journalctl -u displaywall-mgr -f
```

## Einschraenkungen

- **Web-Content:** URLs (Webseiten) werden nur auf Display 1 unterstuetzt. Display 2 kann Bilder und Videos anzeigen.
- **Rotation:** Kernel-Level-Rotation erfordert einen Reboot. Viewer-2 wendet die Rotation sofort auf mpv an.
- **DRM-Master:** Anthias (Display 1) haelt den DRM-Master. Viewer-2 nutzt EGL/DRM (gpu-context), was keinen exklusiven Lock braucht.

## Fehlerbehebung

| Problem | Loesung |
|---------|---------|
| Display 2 zeigt nichts | `sudo systemctl restart anthias-viewer2` |
| "mpv beendete nach 0.7s" im Log | Pruefe ob User `head` in Gruppe `render` ist: `groups head` |
| Web-GUI nicht erreichbar | `sudo systemctl restart displaywall-mgr` |
| Asset erscheint nicht auf Display 2 | Pruefen ob Name mit `2:` beginnt und Asset aktiviert ist |
| Bild wird nicht angezeigt | Pruefe ob die Datei unter `/home/head/screenly_assets/` ein echtes Bild ist: `file <datei>` |
