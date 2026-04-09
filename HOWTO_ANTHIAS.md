# How-To: Installation & Setup "Anthias" (Screenly OSE)

Da die Xibo-Architektur den Raspberry Pi 5 als Player nicht unterstützt, nutzen wir **Anthias** – das beliebteste Open-Source Digital Signage System für den Raspberry Pi. 

**Der große Vorteil:** Es gibt keinen komplexen "Head-Server" mehr. Alle drei Pis sind absolut gleich aufgebaut und unabhängig. Jeder Pi bekommt seine eigene kleine Web-Oberfläche, über die du das Video (das Drittel der Wand) einfach vom Laptop hochlädst.

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
   sudo ./setup-anthias.sh
   ```

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

*(Diesen Vorgang machst du für alle 3 Pis. Da das Setup jetzt extrem leicht ist, bist du in 30 Minuten mit der kompletten Wand fertig).*
