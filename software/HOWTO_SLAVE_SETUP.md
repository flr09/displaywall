# HOWTO: Slave-Pi Setup (Displaywall)

Manuelle Schritt-fuer-Schritt-Anleitung fuer einen frisch geflashten Slave-Pi
(Raspberry Pi 5, Debian 13 "trixie"). Das alte `setup-slave.sh` ist fuer
Bookworm geschrieben und wird hier **nicht** verwendet.

Status 2026-04-16: slave1 und slave2 wurden nach dieser Anleitung eingerichtet
und laufen produktiv.

---

## 0. Voraussetzungen

- Raspberry Pi 5 + Netzteil + HDMI-Monitor zum ersten Boot
- Ethernet-Kabel vom Slave zum Head-Pi (temporaer, nur fuer Setup)
- Pi-Imager (lokal installiert)
- Head-Pi laeuft, Hotspot `displaywall` aktiv (10.42.0.0/24)

## 1. SD-Karte flashen (Pi-Imager)

**OS:** Raspberry Pi OS (64-bit), Release "trixie" (Debian 13).

**Wichtig:** Gleiche OS-Version wie slave1/slave2/head. Mismatch wurde frueher
aufwaendig rueckgaengig gemacht.

**Advanced options (Zahnrad):**
- Hostname: `slave2` (bzw. `slave1`)
- User: `slave2` / Passwort: `12345678`
- SSH: Public-Key-Auth, Key = `~/.ssh/id_ed25519_pi.pub` vom Head
- WLAN: `gaengeviertel` / `KommInDieGaenge!` (Land: DE)
  → nur fuer den allerersten Boot, wird spaeter ersetzt

## 2. Erster Boot + SSH-Zugang

Karte einlegen, Pi booten (dauert ~2 min bis firstboot durch ist).

Lokale `~/.ssh/config` erweitern:

```
Host slave2-pi
    HostName 10.42.0.23
    User slave2
    IdentityFile ~/.ssh/id_ed25519_pi
    StrictHostKeyChecking no
    ProxyJump head-pi
```

IP-Vergabe: slave1 = 10.42.0.22, slave2 = 10.42.0.23.

Beim ersten Kontakt ist der Slave noch im gaengeviertel-Netz, nicht im
Displaywall-Hotspot. SSH geht dann **direkt** (nicht via head-pi).

## 3. apt-Pakete installieren (im gaengeviertel-Netz)

```bash
ssh <slave-im-gaengeviertel>
sudo apt update
sudo apt install -y mpv labwc python3 rsync curl
```

Grund fuer den Schritt: Der Displaywall-Hotspot auf dem Head hat keinen
Uplink, d.h. apt schlaegt fehl sobald der Slave nur noch im 10.42.0.0/24
haengt. Pakete muessen vorher im gaengeviertel-Netz gezogen werden.

## 4. Statische IP im Displaywall-Netz (NetworkManager/netplan)

Auf dem Slave als root:

```bash
sudo tee /etc/netplan/90-displaywall.yaml > /dev/null <<'EOF'
network:
  version: 2
  wifis:
    wlan0:
      renderer: NetworkManager
      match: {}
      dhcp4: false
      addresses:
        - 10.42.0.23/24     # slave1: 10.42.0.22
      routes:
        - to: default
          via: 10.42.0.1
      nameservers:
        addresses: [10.42.0.1]
      access-points:
        "displaywall":
          auth:
            key-management: "psk"
            password: "68c8e22f37e0eb8efcb6a2d29e68162b178941f9b2f679de29d1682d427f5f8e"
EOF
sudo chmod 600 /etc/netplan/90-displaywall.yaml
sudo netplan apply
```

Danach verbindet sich der Slave mit dem Displaywall-Hotspot und hat die
feste IP. SSH ab jetzt nur noch via `ssh slave2-pi` (ProxyJump ueber head-pi).

## 5. tty1-Autologin

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin slave2 --noclear %I \$TERM
EOF
sudo systemctl set-default multi-user.target
sudo systemctl daemon-reload
```

## 6. labwc-Startup + unsichtbarer Cursor

Vom Repo auf den Slave:

```bash
# Annahme: Repo unter /home/chris/displaywall/software/slave-templates/
rsync -av slave-templates/bash_profile.tmpl slave2-pi:.bash_profile
rsync -av slave-templates/config/ slave2-pi:.config/

# Cursor-Theme
rsync -av slave-templates/icons/invisible/ slave2-pi:.icons/invisible/
```

Auf dem Slave in `~/.config/labwc/autostart` den Platzhalter ersetzen:

```bash
ssh slave2-pi "sed -i 's/__SLAVE_USER__/slave2/g' ~/.config/labwc/autostart"
```

Ergebnis:
- `~/.bash_profile` startet labwc beim tty1-Autologin, setzt
  `XCURSOR_THEME=invisible`.
- `~/.config/labwc/environment` + `rc.xml` verstecken den Mauszeiger.
- `~/.config/labwc/autostart` startet `displaywall-agent.py` in einer
  Respawn-Schleife.

## 7. Agent installieren

```bash
ssh slave2-pi "mkdir -p ~/screenly ~/.screenly"
rsync -av displaywall-agent.py displaywall/ slave2-pi:screenly/
```

Port: 8081. Test:

```bash
ssh head-pi "curl -s http://10.42.0.23:8081/api/status"
```

## 8. NOPASSWD-sudo (fuer chvt in .bash_profile)

```bash
ssh slave2-pi "echo 'slave2 ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/slave2"
ssh slave2-pi "sudo chmod 440 /etc/sudoers.d/slave2"
```

## 9. Admin-AP Failover installieren

Das Failover-Script oeffnet einen Admin-AP wenn der Slave das
displaywall-WLAN 3 Minuten nicht findet. AP-SSID = Hostname (slave1/slave2),
Passwort = `12345678`, IP = `192.168.50.1`.

```bash
scp displaywall-failover.sh slave2-pi:failover.sh
scp displaywall-failover.service slave2-pi:failover.service
ssh slave2-pi "sudo cp ~/failover.sh /usr/local/bin/displaywall-failover.sh"
ssh slave2-pi "sudo chmod +x /usr/local/bin/displaywall-failover.sh"
ssh slave2-pi "sudo cp ~/failover.service /etc/systemd/system/displaywall-failover.service"
ssh slave2-pi "sudo systemctl daemon-reload"
ssh slave2-pi "sudo systemctl enable --now displaywall-failover"
```

Verifikation: `sudo journalctl -u displaywall-failover -f`

## 10. slaves.json auf Head aktualisieren

```bash
ssh head-pi 'cat > ~/screenly/displaywall/slaves.json' <<'EOF'
{
  "slave1": {"ip": "10.42.0.22", "port": 8081},
  "slave2": {"ip": "10.42.0.23", "port": 8081}
}
EOF
```

## 10. Reboot + Verifikation

```bash
ssh slave2-pi "sudo reboot"
# ~30s warten
ssh head-pi "curl -s http://10.42.0.23:8081/api/status | jq"
```

Erwartung:
- Monitor zeigt mpv-Fenster (schwarz bis Asset zugewiesen wird).
- Kein Mauszeiger, keine Konsolenmeldungen.
- `/api/status` antwortet mit JSON.

---

## Troubleshooting

- **SSH Permission denied nach Flash:** firstboot laeuft noch. ~1-2 min warten.
- **Host key changed:** `ssh-keygen -R 10.42.0.23` (und analog von head aus).
- **apt kann nichts fetchen:** Slave haengt im Displaywall-Hotspot — der hat
  keinen Uplink. Temporaer ins gaengeviertel-Netz wechseln.
- **Cursor noch sichtbar:** labwc wurde nicht neu gestartet. Auf Slave
  `pkill labwc` (startet via .bash_profile neu) oder reboot.
- **labwc startet nicht, Konsole bleibt:** Pruefen ob `$(tty)` in
  `.bash_profile` korrekt ist (nicht `\$(tty)` — Escaping-Falle bei
  Remote-Heredocs).
