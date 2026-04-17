#!/bin/bash
# install-slave.sh — Displaywall Slave-Pi Setup
#
# Voraussetzungen:
#   - Raspberry Pi 5, Debian 13 "trixie" (64-bit)
#   - SD-Karte geflasht mit Pi Imager (User: slave1/slave2/..., Pass: 12345678)
#   - Pi ist per Ethernet oder WLAN erreichbar
#   - Pakete wurden VOR dem Wechsel ins displaywall-Netz installiert
#     (das displaywall-Netz hat keinen Internet-Uplink!)
#
# Ausfuehren:
#   sudo ./install-slave.sh [SLAVE_IP]
#
# Beispiel:
#   sudo ./install-slave.sh 10.42.0.22
#
# Ohne IP-Argument wird die IP aus dem Hostnamen abgeleitet:
#   slave1 → 10.42.0.22, slave2 → 10.42.0.23, slave3 → 10.42.0.24, ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(hostname)"
USER_HOME="/home/${USER_NAME}"
SCREENLY_DIR="${USER_HOME}/screenly"
HEAD_IP="10.42.0.10"

# IP-Adresse bestimmen
if [ -n "${1:-}" ]; then
    SLAVE_IP="$1"
else
    # Aus Hostname ableiten: slave1 → 22, slave2 → 23, ...
    SLAVE_NUM=$(echo "$USER_NAME" | grep -oP '\d+' || echo "")
    if [ -z "$SLAVE_NUM" ]; then
        echo "FEHLER: Hostname '$USER_NAME' enthaelt keine Nummer."
        echo "Bitte IP als Argument angeben: sudo $0 10.42.0.22"
        exit 1
    fi
    SLAVE_IP="10.42.0.$((21 + SLAVE_NUM))"
fi

# --- Farben ---
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[${USER_NAME}]${NC} $*"; }
err() { echo -e "${RED}[FEHLER]${NC} $*" >&2; }

# Root-Check
if [ "$(id -u)" -ne 0 ]; then
    err "Bitte als root ausfuehren: sudo $0"
    exit 1
fi

log "Slave-Setup: ${USER_NAME} (IP: ${SLAVE_IP})"

# --- 1. Pakete ---
log "Installiere Pakete..."
# WICHTIG: Dieser Schritt braucht Internet!
# Wenn der Pi bereits im displaywall-Netz ist (kein Internet),
# muessen die Pakete vorher installiert worden sein.
if apt-get update -qq 2>/dev/null; then
    apt-get install -y -qq mpv labwc python3 rsync curl
else
    log "apt nicht erreichbar — Pakete muessen bereits installiert sein"
    for pkg in mpv labwc python3; do
        if ! dpkg -l "$pkg" >/dev/null 2>&1; then
            err "Paket '$pkg' fehlt! Bitte zuerst in einem Netz mit Internet installieren."
            exit 1
        fi
    done
fi

# --- 2. Autologin auf tty1 ---
log "Konfiguriere Autologin..."
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${USER_NAME} --noclear %I \$TERM
EOF
systemctl set-default multi-user.target
systemctl daemon-reload

# --- 3. labwc + unsichtbarer Cursor ---
log "Konfiguriere labwc + Cursor..."
sudo -u "$USER_NAME" mkdir -p "${USER_HOME}/.config/labwc"
sudo -u "$USER_NAME" mkdir -p "${USER_HOME}/.icons/invisible/cursors"

# .bash_profile
cat > "${USER_HOME}/.bash_profile" <<'PROFILE'
[ -f ~/.profile ] && . ~/.profile

if [ "$(tty)" = "/dev/tty1" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    export WLR_BACKENDS=drm
    export WLR_LIBINPUT_NO_DEVICES=1
    export WLR_NO_HARDWARE_CURSORS=1
    export XCURSOR_THEME=invisible
    export XCURSOR_SIZE=1
    sudo chvt 1
    exec labwc
fi
PROFILE
chown "$USER_NAME:$USER_NAME" "${USER_HOME}/.bash_profile"

# labwc environment
cat > "${USER_HOME}/.config/labwc/environment" <<'ENV'
WLR_NO_HARDWARE_CURSORS=1
XCURSOR_THEME=invisible
XCURSOR_SIZE=1
ENV

# labwc rc.xml
cat > "${USER_HOME}/.config/labwc/rc.xml" <<'RCXML'
<?xml version="1.0" encoding="UTF-8"?>
<labwc_config>
  <core>
    <decoration>server</decoration>
  </core>
  <theme>
    <name>invisible</name>
    <cornerRadius>0</cornerRadius>
  </theme>
  <cursor>
    <theme>invisible</theme>
    <size>1</size>
    <hide>true</hide>
    <hideTimeout>1</hideTimeout>
  </cursor>
  <windowRules>
    <windowRule identifier="*">
      <serverDecoration>no</serverDecoration>
    </windowRule>
  </windowRules>
</labwc_config>
RCXML

# Unsichtbarer Cursor
if [ -d "${SCRIPT_DIR}/software/slave-templates/icons/invisible" ]; then
    cp -r "${SCRIPT_DIR}/software/slave-templates/icons/invisible/"* \
        "${USER_HOME}/.icons/invisible/"
else
    python3 -c "
import struct, os
hdr = struct.pack('<4sI', b'Xcur', 0x10010)
toc = struct.pack('<III', 0xFFFD0002, 24, 36)
img = struct.pack('<IIIII', 36, 0xFFFD0002, 1, 1, 0) + struct.pack('<I', 0)
d = '${USER_HOME}/.icons/invisible/cursors'
os.makedirs(d, exist_ok=True)
for name in ['default','left_ptr','arrow','hand2','watch','xterm']:
    with open(f'{d}/{name}', 'wb') as f:
        f.write(hdr + toc + img)
with open('${USER_HOME}/.icons/invisible/index.theme', 'w') as f:
    f.write('[Icon Theme]\nName=invisible\nComment=Invisible cursor\nInherits=default\n')
"
fi
chown -R "$USER_NAME:$USER_NAME" "${USER_HOME}/.icons" "${USER_HOME}/.config/labwc"

# --- 4. labwc Autostart (Agent) ---
log "Konfiguriere Agent-Autostart..."
cat > "${USER_HOME}/.config/labwc/autostart" <<AUTOSTART
pkill -f "displaywall-agent.py" 2>/dev/null
killall mpv 2>/dev/null
sleep 1
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
export DISPLAYWALL_HEAD=${HEAD_IP}
(while true; do
    /usr/bin/python3 /home/${USER_NAME}/screenly/displaywall-agent.py >> /home/${USER_NAME}/.screenly/agent.log 2>&1
    echo "[autostart] displaywall-agent.py beendet (\$(date)) — Neustart in 2s" >> /home/${USER_NAME}/.screenly/agent.log
    sleep 2
done) &
AUTOSTART
chown "$USER_NAME:$USER_NAME" "${USER_HOME}/.config/labwc/autostart"

# --- 5. Agent deployen ---
log "Deploye Agent..."
sudo -u "$USER_NAME" mkdir -p "$SCREENLY_DIR" "${USER_HOME}/.screenly" "${USER_HOME}/displaywall_assets"

if [ -f "${SCRIPT_DIR}/software/displaywall-agent.py" ]; then
    cp "${SCRIPT_DIR}/software/displaywall-agent.py" "$SCREENLY_DIR/"

    # displaywall-Modul (fuer Imports, falls benoetigt)
    if [ -d "${SCRIPT_DIR}/software/displaywall" ]; then
        cp -r "${SCRIPT_DIR}/software/displaywall" "$SCREENLY_DIR/"
    fi

    chown -R "$USER_NAME:$USER_NAME" "$SCREENLY_DIR"
else
    err "displaywall-agent.py nicht gefunden in ${SCRIPT_DIR}/software/"
    exit 1
fi

# --- 6. Admin-AP Failover ---
log "Installiere Admin-AP Failover..."
if [ -f "${SCRIPT_DIR}/software/displaywall-failover.sh" ]; then
    cp "${SCRIPT_DIR}/software/displaywall-failover.sh" /usr/local/bin/
    chmod +x /usr/local/bin/displaywall-failover.sh
fi
if [ -f "${SCRIPT_DIR}/software/displaywall-failover.service" ]; then
    cp "${SCRIPT_DIR}/software/displaywall-failover.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable displaywall-failover
fi

# --- 7. Statische IP im displaywall-Netz ---
log "Konfiguriere statische IP (${SLAVE_IP})..."
cat > /etc/netplan/90-displaywall.yaml <<NETPLAN
network:
  version: 2
  wifis:
    wlan0:
      renderer: NetworkManager
      match: {}
      dhcp4: false
      addresses:
        - ${SLAVE_IP}/24
      routes:
        - to: default
          via: 10.42.0.1
      nameservers:
        addresses: [10.42.0.1]
      access-points:
        "displaywall":
          auth:
            key-management: "psk"
            password: "12345678"
NETPLAN
chmod 600 /etc/netplan/90-displaywall.yaml

# --- 8. NOPASSWD-sudo ---
log "Konfiguriere sudo..."
echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USER_NAME}"
chmod 440 "/etc/sudoers.d/${USER_NAME}"

# --- 9. apt-daily deaktivieren ---
log "Deaktiviere apt-daily..."
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
systemctl mask apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true

# --- Fertig ---
log ""
log "========================================="
log "  Slave-Pi Installation abgeschlossen!"
log "========================================="
log ""
log "  Hostname:   ${USER_NAME}"
log "  IP:         ${SLAVE_IP}"
log "  Head:       ${HEAD_IP}"
log "  Agent-Port: 8081"
log "  Admin-AP:   SSID=${USER_NAME}, Pass=12345678"
log ""
log "  Naechster Schritt:"
log "    1. sudo netplan apply  (oder sudo reboot)"
log "    2. Auf dem Head slaves.json erweitern:"
log "       ssh head 'cat ~/screenly/displaywall/slaves.json'"
log ""
log "  Nach dem Reboot:"
log "  - Agent startet automatisch"
log "  - Holt Playlist vom Head (alle 30s)"
log "  - Monitore zeigen Bilder sobald Playlist zugewiesen"
log ""
