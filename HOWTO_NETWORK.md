# How-To: Netzwerk-Konfiguration (Dual-WLAN)

Diese Konfiguration teilt die Netzwerk-Aufgaben des Raspberry Pi 5 auf zwei Schnittstellen auf:
1. **Extern (TP-Link USB):** Verbindung zum Internet/Gängeviertel (Administration).
2. **Intern (Pi-Chip):** Eigenes WLAN-Netzwerk ("Insel") für die Kommunikation der Pis untereinander.

## 1. Administration über den TP-Link USB-Stick (wlan1)

Um den TP-Link Stick mit dem Gängeviertel zu verbinden und eine eigene Administrations-IP zu erhalten:

```bash
# Gängeviertel-Verbindung auf dem USB-Stick (wlan1) einrichten
sudo nmcli device wifi connect "gaengeviertel" password "KommInDieGaenge!" ifname wlan1 name Gaengeviertel-USB
```

Die Administrations-IP für den Head-Pi lautet aktuell: **192.168.193.240**

---

## 2. Internes WLAN-Netzwerk (Insel) auf wlan0 einrichten

Dieser Schritt macht den Head-Pi zum WLAN-Router für die anderen Pis und dein Notebook. 

**Wichtig:** Führe diese Befehle über die Administrations-IP des USB-Sticks aus!

```bash
# 1. Bestehende Gängeviertel-Verbindung vom internen Chip (wlan0) trennen
sudo nmcli device disconnect wlan0

# 2. Den Hotspot (Access Point) anlegen
# Name: displaywall
# Passwort: 12345678
# IP-Adresse des Pis in diesem Netz: 192.168.10.1
sudo nmcli con add type wifi ifname wlan0 con-name Monitorwall-Hotspot autoconnect yes ssid displaywall
sudo nmcli con modify Monitorwall-Hotspot 802-11-wireless.mode ap 802-11-wireless-security.key-mgmt wpa-psk ipv4.method shared 802-11-wireless-security.psk 12345678
sudo nmcli con up Monitorwall-Hotspot
```

Nach diesem Befehl spannt der Pi das WLAN **`displaywall`** auf.

---

## 3. Priorisierung (Internet-Zugang sicherstellen)

Damit der Pi weiß, dass er das Internet über den USB-Stick (Gängeviertel) und nicht über seinen eigenen Hotspot beziehen soll, setzen wir Prioritäten:

```bash
# Gängeviertel (USB) hat Vorrang (niedrigere Metrik = höhere Priorität)
sudo nmcli connection modify Gaengeviertel-USB ipv4.route-metric 100
# Der eigene Hotspot hat Nachrang
sudo nmcli connection modify Monitorwall-Hotspot ipv4.route-metric 200
```

---

## 4. Zugriff auf das Dashboard

Egal in welchem Netz du bist, du erreichst das Anthias-Dashboard nun unter:
*   Über das Gängeviertel (USB-Stick): `http://192.168.193.240`
*   Über das eigene Insel-Netz (Intern): `http://192.168.10.1`
