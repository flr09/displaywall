# How-To: Netzwerk-Konfiguration (Dual-WLAN)

Diese Konfiguration teilt die Netzwerk-Aufgaben des Raspberry Pi 5 auf zwei Schnittstellen auf:
1. **Externer USB-Stick (Admin-WLAN):** Für Internet-Zugang, Software-Updates und Administration.
2. **Interner Pi-Chip (Display-WLAN):** Eigenes WLAN-Netzwerk ("Insel") für die Kommunikation der Pis untereinander.

## 1. Administration über den USB-Stick (wlan1)

Um den USB-Stick mit dem lokalen Admin-WLAN zu verbinden und eine eigene Administrations-IP zu erhalten:

```bash
# Admin-WLAN Verbindung auf dem USB-Stick (wlan1) einrichten
sudo nmcli device wifi connect "DEINE_ADMIN_SSID" password "DEIN_ADMIN_PASSWORT" ifname wlan1 name Admin-USB
```

Die Administrations-IP für den Head-Pi lautet aktuell: **192.168.193.240**

---

## 2. Internes WLAN-Netzwerk (Insel) auf wlan0 einrichten

Dieser Schritt macht den Head-Pi zum WLAN-Router für die anderen Pis und dein Notebook. 

**Wichtig:** Führe diese Befehle über die Administrations-IP des USB-Sticks aus!

```bash
# 1. Bestehende Verbindung vom internen Chip (wlan0) trennen
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

Damit der Pi weiß, dass er das Internet über den USB-Stick (Admin-WLAN) und nicht über seinen eigenen Hotspot beziehen soll, setzen wir Prioritäten:

```bash
# Admin-WLAN (USB) hat Vorrang (niedrigere Metrik = höhere Priorität)
sudo nmcli connection modify Admin-USB ipv4.route-metric 100
# Der eigene Hotspot hat Nachrang
sudo nmcli connection modify Monitorwall-Hotspot ipv4.route-metric 200
```

---

## 4. Zugriff auf das Dashboard

Egal in welchem Netz du bist, du erreichst das Anthias-Dashboard nun unter:
*   Über das Admin-Netzwerk (USB-Stick): `http://192.168.193.240`
*   Über das eigene Insel-Netz (Intern): `http://192.168.10.1`
