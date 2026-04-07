# How-To: Installation & Setup "Head-Pi" (Master)

Diese Anleitung führt dich Schritt für Schritt durch die Installation des "Head-Pi" (Master). Dieser Raspberry Pi steuert nicht nur 2 seiner eigenen Monitore an, sondern hostet auch das zentrale Xibo CMS für alle anderen Pis.

## Vorbereitungen am PC (Mac/Windows/Linux)

1. **Balena Etcher herunterladen:**
   * Lade dir die kostenlose Software **Balena Etcher** herunter: [https://etcher.balena.io/](https://etcher.balena.io/)
   * Installiere und öffne das Programm.

2. **Ubuntu Image herunterladen:**
   * Lade das **Ubuntu Desktop 24.04 LTS (64-bit)** Image speziell für den Raspberry Pi 5 herunter.
   * Link: [Ubuntu for Raspberry Pi](https://ubuntu.com/download/raspberry-pi)

3. **SD-Karte / USB-SSD flashen:**
   * Stecke die MicroSD-Karte (oder USB-SSD) für den Head-Pi in deinen Computer.
   * Öffne Balena Etcher.
   * Wähle *Flash from file* und wähle das heruntergeladene Ubuntu-Image aus.
   * Wähle *Select target* und wähle deine SD-Karte/SSD aus.
   * Klicke auf *Flash!* und warte, bis der Vorgang abgeschlossen ist.

4. **Dateien kopieren:**
   * Kopiere den gesamten Ordner `displaywall/software` (den wir gerade erstellt haben) auf einen USB-Stick. Du wirst ihn gleich auf dem Pi brauchen.

---

## Einrichtung am Head-Pi (Raspberry Pi 5)

### Schritt 1: Erster Start & Betriebssystem-Konfiguration

1. Stecke die geflashte SD-Karte in den Raspberry Pi 5.
2. Schließe Tastatur, Maus, Netzwerkkabel (falls kein WLAN) und die beiden Monitore an.
3. Verbinde das Original 27W Netzteil, um den Pi zu starten.
4. Folge dem Ubuntu-Einrichtungsassistenten (Sprache, Tastatur, WLAN, Benutzerkonto anlegen). **Wichtig:** Merke dir den gewählten Benutzernamen und das Passwort!
5. **Auto-Login aktivieren:**
   * Öffne die Ubuntu *Settings (Einstellungen)* -> *Users (Benutzer)*.
   * Entsperre die Einstellungen oben rechts und aktiviere "Automatic Login".
6. **Grafik-Session prüfen (Optional, falls Ruckeln auftritt):**
   * Ubuntu 24.04 nutzt standardmäßig Wayland. Falls es bei der Videowiedergabe Probleme gibt, melde dich ab. Klicke auf deinen Benutzernamen, dann unten rechts auf das Zahnrad und wähle "Ubuntu on Xorg", bevor du dich wieder anmeldest.

### Schritt 2: Software auf den Pi übertragen

1. Stecke den USB-Stick mit dem `software` Ordner in den Pi.
2. Kopiere den Ordner `software` in dein Benutzerverzeichnis (z.B. `/home/dein-benutzername/`).

### Schritt 3: Grundinstallation starten

1. Öffne ein Terminal (Strg+Alt+T).
2. Wechsle in den kopierten Ordner:
   ```bash
   cd ~/software
   ```
3. Führe das Setup-Skript aus (es installiert Docker und den Xibo Player):
   ```bash
   ./setup.sh
   ```
   *Das Skript wird dich nach deinem Passwort fragen (für `sudo`). Lass es durchlaufen.*

### Schritt 4: Xibo CMS (Zentrale Verwaltung) einrichten

*Dieser Schritt wird NUR auf dem Head-Pi ausgeführt!*

1. Wechsle im Terminal in den entpackten Xibo-Docker Ordner:
   ```bash
   cd ~/software/xibo-docker-*
   ```
2. Kopiere die Konfigurations-Vorlage:
   ```bash
   cp config.env.template config.env
   ```
3. Bearbeite die Konfiguration (mit dem Editor `nano`):
   ```bash
   nano config.env
   ```
   * Suche die Zeile `MYSQL_PASSWORD=` und trage ein sicheres Passwort ein (z.B. `MYSQL_PASSWORD=MeinGeheimesPasswort123`).
   * Speichere mit `Strg+O` (Enter drücken zum Bestätigen) und beende den Editor mit `Strg+X`.
4. Starte das Xibo CMS über Docker:
   ```bash
   sudo docker compose up -d
   ```
   *(Docker lädt nun alle nötigen Server-Komponenten herunter und startet sie im Hintergrund. Das dauert einige Minuten.)*

### Schritt 5: CMS aufrufen & Player verbinden

1. Öffne den Firefox-Browser auf dem Pi (oder an einem anderen PC im Netzwerk).
2. Rufe die Adresse `http://localhost` (oder die IP-Adresse des Head-Pis, z.B. `http://192.168.1.50`) auf.
3. Logge dich in das Xibo CMS ein:
   * **Benutzer:** `xibo_admin`
   * **Passwort:** `password` (Bitte sofort nach dem Login ändern!)
4. Gehe im CMS auf *Displays* -> *Displays*.
5. Starte nun den Xibo Player auf dem Pi (findest du in den installierten Programmen).
6. Der Player fragt nach einer CMS-URL und einem Key.
   * **CMS URL:** `http://localhost` (oder die lokale IP)
   * **Key:** Findest du im CMS unter *Administration* -> *Settings*.
7. Nach der Eingabe taucht der Player im CMS unter "Displays" auf. Dort musst du ihn autorisieren ("Authorise").

Der "Head-Pi" ist nun fertig eingerichtet! Er steuert seine Monitore an und ist gleichzeitig der Server für die beiden anderen Pis.
