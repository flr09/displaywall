#!/bin/bash
# install-head.sh — Displaywall Head-Pi Setup
#
# Voraussetzungen:
#   - Raspberry Pi 5, Debian 13 "trixie" (64-bit)
#   - SD-Karte geflasht mit Pi Imager (User: head, Pass: 12345678)
#   - Pi ist im displaywall-WLAN oder per Ethernet erreichbar
#   - Dieses Script liegt im selben Verzeichnis wie das displaywall-Repo
#
# Ausfuehren:
#   sudo ./install-head.sh
#
# Was passiert:
#   1. Pakete installieren (mpv, labwc, python3, pillow, ...)
#   2. Autologin + labwc als Wayland-Compositor
#   3. Unsichtbarer Cursor
#   4. Displaywall-Software deployen
#   5. Systemd-Services einrichten (Manager, Watchdog)
#   6. Viewer-Autostart via labwc
#   7. NOPASSWD-sudo
#   8. apt-daily deaktivieren

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="head"
USER_HOME="/home/${USER_NAME}"
SCREENLY_DIR="${USER_HOME}/screenly"
ASSET_DIR="${USER_HOME}/screenly_assets"

# --- Farben ---
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[HEAD]${NC} $*"; }
err() { echo -e "${RED}[FEHLER]${NC} $*" >&2; }

# Root-Check
if [ "$(id -u)" -ne 0 ]; then
    err "Bitte als root ausfuehren: sudo $0"
    exit 1
fi

# --- 1. Pakete ---
log "Installiere Pakete..."
apt-get update -qq
apt-get install -y -qq mpv labwc python3 python3-pip python3-pil rsync curl socat jq

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

# Unsichtbarer Cursor (leerer Xcursor)
if [ -d "${SCRIPT_DIR}/software/slave-templates/icons/invisible" ]; then
    cp -r "${SCRIPT_DIR}/software/slave-templates/icons/invisible/"* \
        "${USER_HOME}/.icons/invisible/"
else
    # Minimalen Cursor erzeugen (1x1 transparent)
    python3 -c "
import struct, os
# Xcursor-Format: Header + TOC + Image (1x1 transparent)
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

# --- 4. Software deployen ---
log "Deploye Displaywall-Software..."
sudo -u "$USER_NAME" mkdir -p "$SCREENLY_DIR" "$ASSET_DIR" "${USER_HOME}/.screenly"

# Repo-Dateien kopieren
if [ -d "${SCRIPT_DIR}/software" ]; then
    cp "${SCRIPT_DIR}/software/viewer.py" "$SCREENLY_DIR/"
    cp "${SCRIPT_DIR}/software/displaywall-mgr.py" "$SCREENLY_DIR/"
    cp "${SCRIPT_DIR}/software/displaywall-watchdog.py" "$SCREENLY_DIR/"
    cp -r "${SCRIPT_DIR}/software/displaywall" "$SCREENLY_DIR/"

    # Web-GUI
    if [ -d "${SCRIPT_DIR}/software/webui" ]; then
        cp -r "${SCRIPT_DIR}/software/webui" "$SCREENLY_DIR/"
    fi

    chown -R "$USER_NAME:$USER_NAME" "$SCREENLY_DIR"
else
    err "Verzeichnis ${SCRIPT_DIR}/software nicht gefunden!"
    err "Script muss aus dem Repo-Root ausgefuehrt werden."
    exit 1
fi

# slaves.json (leer, wird spaeter befuellt)
if [ ! -f "${SCREENLY_DIR}/displaywall/slaves.json" ]; then
    echo '{}' > "${SCREENLY_DIR}/displaywall/slaves.json"
    chown "$USER_NAME:$USER_NAME" "${SCREENLY_DIR}/displaywall/slaves.json"
fi

# --- 5. labwc Autostart (Viewer) ---
log "Konfiguriere Viewer-Autostart..."
cat > "${USER_HOME}/.config/labwc/autostart" <<'AUTOSTART'
pkill -f "viewer.py" 2>/dev/null
killall mpv 2>/dev/null
sleep 1

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000

(while true; do
    /usr/bin/python3 /home/head/screenly/viewer.py --displays head-1:HDMI-A-1,head-2:HDMI-A-2 >> /home/head/.screenly/viewer.log 2>&1
    echo "[autostart] viewer.py beendet ($(date)) — Neustart in 2s" >> /home/head/.screenly/viewer.log
    sleep 2
done) &
AUTOSTART
chown "$USER_NAME:$USER_NAME" "${USER_HOME}/.config/labwc/autostart"

# --- 6. Systemd-Services ---
log "Installiere Systemd-Services..."

# Displaywall Manager (Web-GUI)
cat > /etc/systemd/system/displaywall-mgr.service <<EOF
[Unit]
Description=Displaywall Manager Web-GUI
After=network.target

[Service]
Type=simple
User=${USER_NAME}
ExecStart=/usr/bin/python3 ${SCREENLY_DIR}/displaywall-mgr.py
Restart=always
RestartSec=5
Environment=HOME=${USER_HOME}

[Install]
WantedBy=multi-user.target
EOF

# Watchdog
cat > /etc/systemd/system/displaywall-watchdog.service <<EOF
[Unit]
Description=Displaywall Watchdog
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 ${SCREENLY_DIR}/displaywall-watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable displaywall-mgr displaywall-watchdog
systemctl start displaywall-mgr displaywall-watchdog

# --- 7. NOPASSWD-sudo ---
log "Konfiguriere sudo..."
echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USER_NAME}"
chmod 440 "/etc/sudoers.d/${USER_NAME}"

# --- 8. apt-daily deaktivieren ---
log "Deaktiviere apt-daily (verhindert Systemwarnungen auf Displays)..."
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
systemctl mask apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true

# --- 9. Statische IP (optional, fuer displaywall-Netz) ---
log "Konfiguriere statische IP..."
if [ ! -f /etc/netplan/90-displaywall.yaml ]; then
    cat > /etc/netplan/90-displaywall.yaml <<'NETPLAN'
network:
  version: 2
  wifis:
    wlan0:
      renderer: NetworkManager
      match: {}
      dhcp4: false
      addresses:
        - 10.42.0.10/24
      routes:
        - to: default
          via: 10.42.0.1
      nameservers:
        addresses: [10.42.0.1, 8.8.8.8]
      access-points:
        "displaywall":
          auth:
            key-management: "psk"
            password: "12345678"
NETPLAN
    chmod 600 /etc/netplan/90-displaywall.yaml
    log "Statische IP konfiguriert (10.42.0.10). Wird nach Reboot aktiv."
fi

# --- Fertig ---
log ""
log "========================================="
log "  Head-Pi Installation abgeschlossen!"
log "========================================="
log ""
log "  Web-GUI:    http://10.42.0.10:8080"
log "  SSH:        ssh head@10.42.0.10"
log "  Passwort:   12345678"
log ""
log "  Naechster Schritt: sudo reboot"
log ""
log "  Nach dem Reboot:"
log "  - Monitore zeigen den Viewer (schwarz bis Assets zugewiesen)"
log "  - Web-GUI ist erreichbar"
log "  - Slaves koennen eingerichtet werden"
log ""
