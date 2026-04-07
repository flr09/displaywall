# How-To: Installation & Setup "Client-Pis" (Headless / Slaves)

Diese Anleitung führt dich durch die Installation der beiden "Client-Pis". Diese Raspberry Pis benötigen kein CMS (das läuft ja schon auf dem Head-Pi), sondern müssen nur den **Xibo Player** ausführen.
Dank der "Headless"-Installation sparst du dir hierbei das Anschließen von Tastaturen und das Durchklicken der Installationsassistenten auf den Pis.

## Vorbereitungen am PC (Mac/Windows/Linux)

1. **Raspberry Pi Imager herunterladen:**
   * Anstelle von Balena Etcher nutzen wir hier den offiziellen Raspberry Pi Imager. Dieser kann das Betriebssystem *vor* dem Flashen automatisch konfigurieren.
   * Lade ihn herunter und installiere ihn: [https://www.raspberrypi.com/software/](https://www.raspberrypi.com/software/)
   * Starte das Programm.

2. **OS Customisation (Der Headless-Trick!):**
   * Wähle das Raspberry Pi Device (Pi 5).
   * Klicke bei **Betriebssystem** auf `Raspberry Pi OS (Other)` -> `Ubuntu` -> `Ubuntu Desktop 24.04 LTS (64-bit)`.
   * Wähle deine MicroSD-Karte (Storage) aus.
   * **WICHTIG:** Klicke jetzt auf **NEXT** und wenn die Abfrage kommt "Use OS customisation?", wähle **EDIT SETTINGS**.

3. **Einstellungen (OS Customisation):**
   * Setze den Haken bei **Set hostname** (z.B. `client-pi-1`, für die nächste Karte dann `client-pi-2`).
   * Setze den Haken bei **Set username and password**. Erstelle einen Benutzer (z.B. `xibo_user`) und ein Passwort.
   * Setze den Haken bei **Configure wireless LAN** und trage dein WLAN-Netzwerk (SSID) und das WLAN-Passwort ein.
   * Gehe oben auf den Reiter **SERVICES**.
   * Setze den Haken bei **Enable SSH** und wähle **Use password authentication**.
   * Speichere die Einstellungen (`SAVE`) und klicke auf `YES`, um das Image zu flashen.

---

## Einrichtung am Client-Pi über das Netzwerk

1. **Booten:** Stecke die fertige SD-Karte in den Pi. Verbinde Strom und Monitore. Warte ca. 3-5 Minuten. Der Pi richtet im Hintergrund alles ein und verbindet sich mit dem WLAN.
2. **IP-Adresse herausfinden:**
   * Wenn du den Pi an den Monitor angeschlossen hast, siehst du, sobald der Bootvorgang abgeschlossen ist, oben rechts ein Netzwerk-Icon. Manchmal muss man sich hier doch kurz einloggen und auf Eigenschaften klicken, oder du schaust in deinem Router nach der IP von `client-pi-1`.
3. **SSH Verbindung herstellen:**
   * Öffne am PC (Windows: PowerShell, Mac/Linux: Terminal).
   * Verbinde dich per SSH mit dem Pi:
     ```bash
     ssh xibo_user@IP_ADRESSE_DES_PIS
     ```
   * *Tipp:* Du kannst oft auch `ssh xibo_user@client-pi-1.local` verwenden, wenn dein Netzwerk mDNS unterstützt.
   * Bestätige die erste Verbindung mit `yes` und gib dein Passwort ein (es werden keine Sternchen angezeigt).

### Software-Installation über SSH (Fernsteuerung)

Du bist nun per Kommandozeile mit dem Pi verbunden. Wir laden nun das Client-Setup-Skript herunter und führen es aus.

1. Lade das Skript von Github (falls es öffentlich ist) oder kopiere es per `scp` von deinem PC auf den Pi. Alternativ, falls du es auf einen USB-Stick gelegt hast, wechsle auf den Stick. Da du SSH hast, ist der einfachste Weg, den Dateiinhalt des Skripts direkt anzulegen. Wir machen es ganz einfach:
   Erstelle eine neue Datei auf dem Pi:
   ```bash
   nano setup-client.sh
   ```
2. **Kopiere den Inhalt** aus der lokalen `displaywall/software/setup-client.sh` (die wir zuvor erstellt haben) von deinem PC und füge ihn (Rechtsklick) in das Fenster auf dem Pi ein.
3. Speichere mit `Strg+O` (Enter) und schließe mit `Strg+X`.
4. Mache das Skript ausführbar und starte es:
   ```bash
   chmod +x setup-client.sh
   sudo ./setup-client.sh
   ```
   *Dieses Skript installiert den Player, erzwingt X11 für bessere Beschleunigung und richtet den Autostart ein.*

## Abschluss am Pi-Monitor

Das Skript ist fertig, und der Pi wurde neu gestartet.

1. Der Ubuntu-Desktop lädt (Auto-Login ist oft bei Desktop Images nicht aktiv über Imager, ggf. also einmal am Display auf "Automatische Anmeldung" in den Einstellungen stellen).
2. Der Xibo Player öffnet sich dank Autostart selbstständig.
3. **Letzter manueller Schritt:** Schließe hier für 2 Minuten eine Maus an. Trage im sich öffnenden Fenster die **CMS-URL** (Die IP des Head-Pis, z.B. `http://192.168.1.50`) und den **Key** (Aus dem CMS-Menü) ein.
4. Klicke auf "Save".

Der Pi lädt jetzt das zugewiesene Layout vom Head-Pi und startet die Videowall! Diesen Vorgang wiederholst du einfach für den zweiten Client-Pi.
