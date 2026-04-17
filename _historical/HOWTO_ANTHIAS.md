# How-To: Installation & Setup "Anthias" (Screenly OSE)

Da die Xibo-Architektur den Raspberry Pi 5 als Player nicht unterstützt, nutzen wir **Anthias** -- das beliebteste Open-Source Digital Signage System fuer den Raspberry Pi. 

**Der grosse Vorteil:** Es gibt keinen komplexen "Head-Server" mehr. Alle drei Pis sind absolut gleich aufgebaut und unabhaengig. Jeder Pi bekommt seine eigene kleine Web-Oberflaeche, ueber die du das Video (das Drittel der Wand) einfach vom Laptop hochlaedst.

## Standard-Zugangsdaten

| Was | Wert |
|-----|------|
| **Hostname** | `head.local` / `pi-links.local` / `pi-mitte.local` / `pi-rechts.local` |
| **Benutzer** | **`Head`** |
| **Passwort** | **`12345678`** |
| **WLAN (Displaywall)** | SSID: **`DisplayWall-Netzwerk`**, Passwort: **`DisplayPassword123`** |
| **Anthias Dashboard** | **`http://<hostname>.local`** im Browser |

*Diese Zugangsdaten koennen nach der Einrichtung jederzeit geaendert werden (`passwd` fuer den User, `nmcli` fuer WLAN).*

## Vorbereitungen am PC (Mac/Windows/Linux)

1. **Raspberry Pi Imager:**
   * Nutze den Raspberry Pi Imager.
   * Wähle **Raspberry Pi 5**.
   * Wähle das Betriebssystem **Raspberry Pi OS (64-bit)** (Nicht Ubuntu!).
   * Wähle deine SD-Karte und klicke auf *Weiter*.
   
2. **OS Customisation (WLAN & SSH):**
   * Klicke auf *Einstellungen bearbeiten*.
   * Setze den Hostnamen auf z.B. `pi-links`, `pi-mitte`, `pi-rechts`.
   * Lege deinen Benutzer (z.B. `Head`) und das Passwort an.
   * Trage deine WLAN-Daten ein.
   * Aktiviere unter "Dienste" zwingend den **SSH-Zugang mit Passwort**.
   * Speichern und Flashen!

## Einrichtung per SSH (Auf allen 3 Pis identisch)

Stecke die fertig geflashte SD-Karte in den Pi, schließe ihn ans Stromnetz an und warte ca. 2-3 Minuten, bis er hochgefahren ist.

1. **Dateien auf den Pi kopieren:**
   Öffne an deinem PC das Terminal in unserem Projektordner `displaywall` und schiebe den Software-Ordner auf den Pi:
   ```bash
   scp -r software Head@pi-links.local:~/software
   ```
   *(Passe `pi-links.local` natürlich an den Hostnamen des jeweiligen Pis oder seine IP an).*

2. **Per SSH einloggen:**
   ```bash
   ssh Head@pi-links.local
   ```

3. **Den Anthias Installer starten:**
   Sobald du auf dem Pi eingeloggt bist, starte unser neues Installations-Skript:
   ```bash
   cd ~/software
   chmod +x setup-anthias.sh
   ./setup-anthias.sh
   ```
   **(KEIN sudo! Das Skript fragt selbst nach dem Passwort, wo es Root braucht.)**

### Der Anthias Installations-Prozess

Der Installer (der offiziell von Github geladen wird) stellt dir während des Durchlaufs einige Fragen in blauen Fenstern (oder per Y/N-Abfrage):

*   **"Do you want to continue?"** -> `Y` (Yes)
*   **"Manage network with NetworkManager?"** -> `Y` (Besser für die WLAN-Stabilität).
*   **"System Upgrade?"** -> `Y` (Obwohl unser Skript das schon gemacht hat, sicher ist sicher).
*   Am Ende sagt er: **"Installation complete! Reboot needed."** -> Bestätige den Reboot.

## Die Bedienung (Dein neues CMS)

Nach dem Neustart bootet der Pi von ganz alleine direkt in einen schwarzen "Anthias"-Bildschirm (der Kiosk-Modus).

1. Auf diesem schwarzen Bildschirm (oder im Terminal, kurz vor dem Reboot) steht eine **IP-Adresse** (z.B. `192.168.193.105`).
2. Öffne den Browser an deinem normalen Laptop (der im selben WLAN ist).
3. Tippe diese IP-Adresse ein.
4. **Fertig!** Du siehst das super einfache Anthias-Dashboard.
   * Klicke auf "Add Asset" (Asset hinzufügen).
   * Lade dein in 3 Teile geschnittenes MP4-Video hoch.
   * Schiebe es in den "Active" (Aktiv) Schalter und lösche ggf. die Demobilder heraus.
   * Das Video läuft sofort los.

*(Diesen Vorgang machst du fuer alle 3 Pis. Da das Setup jetzt extrem leicht ist, bist du in 30 Minuten mit der kompletten Wand fertig).*

## Stromversorgung (Waveshare Pi5-Module-BOX)

Die Pis stecken in **Waveshare Pi5-Module-BOX** Gehaeusen. Diese haben einen rueckseitigen Stromanschluss, der ueber einen MOSFET (AO4407A) direkt auf den USB-C des Pi durchleitet. **Es findet keine USB-PD-Negotiation statt.**

### Einschraenkungen

- Der Adapter hat **keinen Spannungsregler** -- die Eingangsspannung kommt direkt am Pi an (minus ~0.2-0.3V Verlust durch MOSFET + Leiterbahnen).
- Bei einem Standard-5V-Netzteil kommen nur ~4.4-4.7V am Pi an. Das fuehrt unter Last (Video-Upload, Wiedergabe) zu **Undervoltage-Throttling und Abstuerzen**.
- `usb_max_current_enable=1` (Pi 4 Setting) hat auf dem Pi 5 **keinen Effekt**.
- `avoid_warnings=2` wird vom Setup-Skript gesetzt, damit im Betrieb **keine Warnungen auf den Displays** erscheinen. Undervoltage-Monitoring laeuft stattdessen ueber `monitor-power.sh` per SSH.

### Loesung

Die Ausgangsspannung am Netzteil muss auf **ca. 5.4-5.5V** hochgedreht werden, damit nach den Verlusten im Adapter noch **>4.8V** am Pi ankommen.

**Nicht ueber 5.8V am Netzteil gehen** -- der Pi 5 hat einen Overvoltage-Schutz bei 5.5V am USB-C Eingang.

### Spannung pruefen

Per SSH auf dem Pi:
```bash
vcgencmd pmic_read_adc EXT5V_V    # Spannung (Ziel: >4.8V, stabil)
vcgencmd pmic_read_adc EXT5V_I    # Strom
vcgencmd get_throttled             # 0x0 = OK, 0x50000 = Problem
```

### Monitoring-Tool

Im `software/`-Ordner liegt das Skript `monitor-power.sh`. Es loggt Spannung, Strom und Throttle-Status ueber einen Zeitraum in eine CSV-Datei:

```bash
cd ~/software
chmod +x monitor-power.sh
./monitor-power.sh          # Standard: 60 Sekunden
./monitor-power.sh 300      # 5 Minuten Langzeitmessung
```

Die CSV-Datei wird in `~/power-log_DATUM.csv` gespeichert und kann zur Fehleranalyse verwendet werden.
