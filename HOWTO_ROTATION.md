# How-To: Bildschirme drehen (Portrait / Hochkant) per Fernsteuerung

Bei einer Videowall-Installation mit Raspberry Pi OS (Bookworm, 64-bit) auf einem Pi 5 übernimmt der moderne Desktopmanager **Wayland (Wayfire)** die Bildschirmausgabe. 

Mit dem mitgelieferten kleinen Skript `rotate-screen.sh` kannst du die Bildschirme ganz bequem per SSH von der Couch aus drehen und sofort live auf der Videowall sehen, was passiert.

## Voraussetzungen
* Die Pis sind eingerichtet (siehe `HOWTO_INSTALL.md` und `HOWTO_CLIENTS.md`).
* Du bist per SSH mit dem jeweiligen Pi verbunden (z.B. `ssh Head@192.168.193.105`).
* Du hast den Ordner `software` bereits auf den Pi kopiert (z.B. mit `scp -r displaywall/software Head@192.168.193.105:~/software`).

## Die Monitore drehen (Live-Test)

1. **Wechsle in den Software-Ordner:**
   ```bash
   cd ~/software
   chmod +x rotate-screen.sh
   ```

2. **Lass dir die angeschlossenen Monitore anzeigen:**
   Wenn du das Skript ohne Zusätze ausführst, gibt es dir eine kleine Liste (z.B. `HDMI-A-1` und `HDMI-A-2`):
   ```bash
   ./rotate-screen.sh
   ```

3. **Den Bildschirm um 90 Grad drehen (Hochkant):**
   Wenn der erste Monitor (HDMI-A-1) in den Hochkant-Modus soll, tippe einfach:
   ```bash
   ./rotate-screen.sh HDMI-A-1 90
   ```
   *(Der Bildschirm dreht sich sofort. Falls er auf dem Kopf steht, nimm statt `90` einfach `270`).*

## Die Drehung DAUERHAFT speichern (Autostart)

Der obige Befehl ist super für den Live-Test, um zu sehen, ob links und rechts richtig zugewiesen sind. Nach einem Pi-Neustart wäre die Drehung aber wieder weg.

Damit der Pi sich das für immer merkt, schreiben wir die Konfiguration direkt in seine Start-Datei (`wayfire.ini`).

1. **Öffne die Konfigurationsdatei des Bildschirms auf dem Pi:**
   ```bash
   nano ~/.config/wayfire.ini
   ```

2. **Füge ganz am Ende der Datei einen neuen Block für deinen Monitor ein:**
   Suche nach einem Abschnitt, der z.B. `[output:HDMI-A-1]` heißt, oder erstelle ihn einfach ganz unten:
   ```ini
   [output:HDMI-A-1]
   transform = 90
   ```
   *(Ersetze `HDMI-A-1` natürlich mit dem Anschluss deines Monitors, den du drehen willst).*

3. **Speichern und Schließen:**
   * Drücke `Strg + O` (dann Enter), um zu speichern.
   * Drücke `Strg + X`, um den Editor zu schließen.

**Das war's!** Egal wie oft der Pi jetzt neu startet (z.B. nach einem Stromausfall der Videowall), er wird diesen Monitor von nun an immer im Hochkantformat laden und den Xibo-Player perfekt in dem neuen Layout (1440 x 2560) starten.
