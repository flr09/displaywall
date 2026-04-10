# How-To: Installation & Setup "Client-Pis" (Slaves)

Diese Anleitung führt dich durch die Einrichtung der beiden Slaves. Da der Head-Pi bereits sein eigenes WLAN **`displaywall`** aufspannt, nutzen wir dies direkt für die Headless-Installation der Slaves.

## 1. SD-Karte flashen (Headless-Vorbereitung)

1. **Raspberry Pi Imager:**
   * Wähle **Raspberry Pi 5** und **Raspberry Pi OS (64-bit)**.
   * Klicke auf *EINSTELLUNGEN BEARBEITEN*.
   * Hostname: `pi-mitte` (bzw. `pi-rechts`).
   * Benutzer/Passwort: Setze deine Daten (z.B. `head` / `12345678`).
   * **WLAN einrichten:**
     * SSID: `displaywall`
     * Passwort: `12345678`
   * **Dienste:** SSH aktivieren (Passwort-Authentifizierung).
   * Karte flashen!

## 2. Einrichtung am Pi über das Netzwerk (SSH)

1. Stecke die Karte in den Slave-Pi und schalte den Strom ein. Der Pi verbindet sich nach dem Booten automatisch mit dem `displaywall`-WLAN des Heads.
2. Der Pi bekommt vom Head eine IP im Bereich `192.168.10.x`.
   *(Du findest die IP im Router-Menü des Heads oder scanne mit `ping pi-mitte.local`).*
3. **Software auf den Slave kopieren (vom Notebook aus):**
   ```bash
   scp -r displaywall/software head@pi-mitte.local:~/software
   ```
4. **Per SSH einloggen:**
   ```bash
   ssh head@pi-mitte.local
   ```
5. **Setup starten:**
   ```bash
   cd ~/software
   chmod +x setup-client.sh
   ./setup-client.sh
   ```
   *(Beantworte alle Fragen im blauen Anthias-Fenster mit **Y** / Yes).*

---

## 3. Bedienung

Jeder Slave hat nach dem Neustart sein eigenes Anthias-Dashboard unter seiner eigenen IP (z.B. `http://192.168.10.50`). 
Du kannst dort das entsprechende Video-Segment hochladen.
