#!/bin/bash
# =============================================================================
# Displaywall Slave-Pi Setup
# =============================================================================
#
# Richtet einen Raspberry Pi 5 als Slave fuer die Displaywall ein.
# Voraussetzungen:
#   - Raspberry Pi OS (Bookworm, 64-bit) frisch installiert
#   - Netzwerkzugang (WLAN oder Ethernet)
#   - SSH aktiviert
#
# Ausfuehren:
#   scp setup-slave.sh <user>@<slave-ip>:~/
#   ssh <user>@<slave-ip> "chmod +x ~/setup-slave.sh && sudo ~/setup-slave.sh"
#
# Konfigurierbare Variablen (vor Ausfuehrung anpassen oder als ENV setzen):
#   SLAVE_HOSTNAME  — z.B. "slave1" oder "slave2"
#   HEAD_PI_IP      — IP des Head-Pi (VJ-Manager)
#   SLAVE_USER      — Benutzer auf dem Slave (default: head)
#   HDMI1_ROTATION  — Rotation HDMI-A-1 in Grad (0/90/180/270)
#   HDMI2_ROTATION  — Rotation HDMI-A-2 in Grad (0/90/180/270)
#   RESOLUTION      — Display-Aufloesung (default: 2560x1440)
# =============================================================================

set -euo pipefail

# --- Konfiguration ---

SLAVE_HOSTNAME="${SLAVE_HOSTNAME:-slave1}"
HEAD_PI_IP="${HEAD_PI_IP:-192.168.193.105}"
SLAVE_USER="${SLAVE_USER:-head}"
HDMI1_ROTATION="${HDMI1_ROTATION:-0}"
HDMI2_ROTATION="${HDMI2_ROTATION:-0}"
RESOLUTION="${RESOLUTION:-2560x1440}"

INSTALL_DIR="/home/${SLAVE_USER}/displaywall"
CONFIG_DIR="/home/${SLAVE_USER}/.displaywall"
ASSET_DIR="/home/${SLAVE_USER}/displaywall_assets"
USB_MOUNT="/media/displaywall"

# Farben fuer Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[SETUP]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Root-Check ---

if [ "$(id -u)" -ne 0 ]; then
    err "Dieses Skript muss als root ausgefuehrt werden (sudo)."
fi

echo ""
echo "============================================"
echo "  Displaywall Slave Setup"
echo "  Hostname: ${SLAVE_HOSTNAME}"
echo "  Head-Pi:  ${HEAD_PI_IP}"
echo "  User:     ${SLAVE_USER}"
echo "============================================"
echo ""

# =============================================================================
# Phase 1: System-Grundlagen
# =============================================================================

log "Phase 1: System-Update und Grundpakete..."

# Hostname setzen
hostnamectl set-hostname "${SLAVE_HOSTNAME}"
sed -i "s/127.0.1.1.*/127.0.1.1\t${SLAVE_HOSTNAME}/" /etc/hosts
log "Hostname gesetzt: ${SLAVE_HOSTNAME}"

# System aktualisieren
apt-get update -qq
apt-get upgrade -y -qq

# Benoetigte Pakete installieren
apt-get install -y -qq \
    mpv \
    python3 \
    python3-pip \
    udisks2 \
    usbutils \
    rsync \
    curl \
    jq \
    htop \
    git

log "Pakete installiert."

# =============================================================================
# Phase 2: Benutzer und Verzeichnisse
# =============================================================================

log "Phase 2: Benutzer und Verzeichnisse..."

# User 'head' existiert auf frischem Pi OS evtl. nicht
if ! id "${SLAVE_USER}" &>/dev/null; then
    useradd -m -s /bin/bash -G video,render,audio,input,plugdev "${SLAVE_USER}"
    log "Benutzer '${SLAVE_USER}' angelegt."
else
    # Sicherstellen, dass Gruppen stimmen
    usermod -aG video,render,audio,input,plugdev "${SLAVE_USER}"
    log "Benutzer '${SLAVE_USER}' existiert, Gruppen aktualisiert."
fi

# Verzeichnisse anlegen
mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${ASSET_DIR}" "${USB_MOUNT}"
chown -R "${SLAVE_USER}:${SLAVE_USER}" "${INSTALL_DIR}" "${CONFIG_DIR}" "${ASSET_DIR}"
log "Verzeichnisse angelegt."

# =============================================================================
# Phase 3: Display-Konfiguration
# =============================================================================

log "Phase 3: Display-Konfiguration..."

# Aufloesung in cmdline.txt setzen
CMDLINE="/boot/firmware/cmdline.txt"
if [ -f "${CMDLINE}" ]; then
    # Bestehende video= Parameter entfernen
    sed -i 's/ video=[^ ]*//g' "${CMDLINE}"

    # Neue video= Parameter anhaengen
    VIDEO_PARAMS="video=HDMI-A-1:${RESOLUTION}@60"
    if [ "${HDMI1_ROTATION}" -ne 0 ]; then
        VIDEO_PARAMS="${VIDEO_PARAMS},rotate=${HDMI1_ROTATION}"
    fi
    VIDEO_PARAMS="${VIDEO_PARAMS} video=HDMI-A-2:${RESOLUTION}@60"
    if [ "${HDMI2_ROTATION}" -ne 0 ]; then
        VIDEO_PARAMS="${VIDEO_PARAMS},rotate=${HDMI2_ROTATION}"
    fi

    sed -i "s/$/ ${VIDEO_PARAMS}/" "${CMDLINE}"
    log "cmdline.txt: ${VIDEO_PARAMS}"
fi

# config.txt: Warnungen unterdruecken
CONFIG_TXT="/boot/firmware/config.txt"
if [ -f "${CONFIG_TXT}" ]; then
    grep -q "avoid_warnings=2" "${CONFIG_TXT}" || echo "avoid_warnings=2" >> "${CONFIG_TXT}"
    log "config.txt: avoid_warnings=2 gesetzt."
fi

# displays.json schreiben
cat > "${CONFIG_DIR}/displays.json" <<DISPEOF
{
  "HDMI-A-1": {"rotation": ${HDMI1_ROTATION}, "resolution": "${RESOLUTION}"},
  "HDMI-A-2": {"rotation": ${HDMI2_ROTATION}, "resolution": "${RESOLUTION}"}
}
DISPEOF
chown "${SLAVE_USER}:${SLAVE_USER}" "${CONFIG_DIR}/displays.json"
log "displays.json geschrieben."

# =============================================================================
# Phase 4: USB Auto-Mount
# =============================================================================

log "Phase 4: USB Auto-Mount einrichten..."

# udev-Regel: USB-Sticks automatisch nach /media/displaywall mounten
cat > /etc/udev/rules.d/99-displaywall-usb.rules <<'UDEVEOF'
# Displaywall: USB-Speicher automatisch mounten
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", \
  ENV{ID_USB_DRIVER}=="usb-storage", \
  RUN+="/usr/local/bin/displaywall-usb-mount.sh add %k"

ACTION=="remove", SUBSYSTEM=="block", ENV{ID_USB_DRIVER}=="usb-storage", \
  RUN+="/usr/local/bin/displaywall-usb-mount.sh remove %k"
UDEVEOF

# Mount-Skript
cat > /usr/local/bin/displaywall-usb-mount.sh <<MOUNTEOF
#!/bin/bash
# Displaywall USB Auto-Mount
USB_MOUNT="${USB_MOUNT}"
ACTION="\$1"
DEVICE="\$2"

if [ "\$ACTION" = "add" ]; then
    mkdir -p "\${USB_MOUNT}"
    # Nur mounten wenn noch nicht gemountet
    if ! mountpoint -q "\${USB_MOUNT}"; then
        mount -o uid=$(id -u ${SLAVE_USER}),gid=$(id -g ${SLAVE_USER}),dmask=022,fmask=133 \
              "/dev/\${DEVICE}" "\${USB_MOUNT}" 2>/dev/null || \
        mount "/dev/\${DEVICE}" "\${USB_MOUNT}" 2>/dev/null
        logger "displaywall: USB gemountet: /dev/\${DEVICE} -> \${USB_MOUNT}"
    fi
elif [ "\$ACTION" = "remove" ]; then
    if mountpoint -q "\${USB_MOUNT}"; then
        umount "\${USB_MOUNT}" 2>/dev/null
        logger "displaywall: USB entfernt: /dev/\${DEVICE}"
    fi
fi
MOUNTEOF
chmod +x /usr/local/bin/displaywall-usb-mount.sh

# udev-Regeln neu laden
udevadm control --reload-rules
log "USB Auto-Mount konfiguriert (${USB_MOUNT})."

# =============================================================================
# Phase 5: Displaywall Agent installieren
# =============================================================================

log "Phase 5: Displaywall Agent installieren..."

# Agent-Skript kopieren (liegt im selben Verzeichnis wie dieses Setup)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/displaywall-agent.py" ]; then
    cp "${SCRIPT_DIR}/displaywall-agent.py" "${INSTALL_DIR}/displaywall-agent.py"
    chmod +x "${INSTALL_DIR}/displaywall-agent.py"
    log "displaywall-agent.py installiert."
else
    warn "displaywall-agent.py nicht gefunden in ${SCRIPT_DIR}."
    warn "Bitte manuell kopieren: scp displaywall-agent.py ${SLAVE_USER}@${SLAVE_HOSTNAME}:${INSTALL_DIR}/"
fi

# =============================================================================
# Phase 6: systemd-Services
# =============================================================================

log "Phase 6: systemd-Services einrichten..."

# Displaywall Agent Service
cat > /etc/systemd/system/displaywall-agent.service <<SVCEOF
[Unit]
Description=Displaywall Slave Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SLAVE_USER}
Environment=DISPLAYWALL_HEAD=${HEAD_PI_IP}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/displaywall-agent.py
Restart=always
RestartSec=5
# CPU-Pinning: Viewer nutzt alle 4 Kerne (kein Docker-Overhead wie auf Head)
# Optional: CPUAffinity=0 1 2 3

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable displaywall-agent.service
log "displaywall-agent.service aktiviert."

# =============================================================================
# Phase 7: SSH-Key vom Head-Pi
# =============================================================================

log "Phase 7: SSH vorbereiten..."

# SSH-Verzeichnis fuer den Slave-User
SLAVE_SSH="/home/${SLAVE_USER}/.ssh"
mkdir -p "${SLAVE_SSH}"
chmod 700 "${SLAVE_SSH}"
touch "${SLAVE_SSH}/authorized_keys"
chmod 600 "${SLAVE_SSH}/authorized_keys"
chown -R "${SLAVE_USER}:${SLAVE_USER}" "${SLAVE_SSH}"

# Head-Pi als bekannten Host eintragen
cat >> "/home/${SLAVE_USER}/.ssh/config" <<SSHEOF

Host head-pi
    HostName ${HEAD_PI_IP}
    User head
    StrictHostKeyChecking accept-new
SSHEOF
chown "${SLAVE_USER}:${SLAVE_USER}" "/home/${SLAVE_USER}/.ssh/config"
chmod 600 "/home/${SLAVE_USER}/.ssh/config"

log "SSH vorbereitet. SSH-Key des Head-Pi muss manuell hinzugefuegt werden:"
log "  ssh-copy-id -i ~/.ssh/id_ed25519_pi.pub ${SLAVE_USER}@${SLAVE_HOSTNAME}"

# =============================================================================
# Phase 8: Netzwerk-Konfiguration
# =============================================================================

log "Phase 8: Netzwerk optimieren..."

# mDNS/Avahi sicherstellen (damit slave1.local erreichbar ist)
apt-get install -y -qq avahi-daemon
systemctl enable avahi-daemon

log "Avahi aktiviert: ${SLAVE_HOSTNAME}.local erreichbar."

# =============================================================================
# Phase 9: Firewall (optional, falls ufw aktiv)
# =============================================================================

if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    ufw allow 8081/tcp comment "Displaywall Agent API"
    ufw allow 22/tcp comment "SSH"
    log "Firewall: Port 8081 und 22 geoeffnet."
fi

# =============================================================================
# Phase 10: Verifikation
# =============================================================================

log "Phase 10: Verifikation..."

echo ""
echo "============================================"
echo "  Setup abgeschlossen!"
echo "============================================"
echo ""
echo "  Hostname:    ${SLAVE_HOSTNAME}"
echo "  Agent-Port:  8081"
echo "  Asset-Dir:   ${ASSET_DIR}"
echo "  USB-Mount:   ${USB_MOUNT}"
echo "  Config-Dir:  ${CONFIG_DIR}"
echo ""
echo "  Naechste Schritte:"
echo "  1. SSH-Key vom Head-Pi kopieren:"
echo "     ssh-copy-id -i ~/.ssh/id_ed25519_pi.pub ${SLAVE_USER}@${SLAVE_HOSTNAME}"
echo ""
echo "  2. REBOOT (noetig fuer Display-Rotation und Hostname):"
echo "     sudo reboot"
echo ""
echo "  3. Nach Reboot pruefen:"
echo "     curl http://${SLAVE_HOSTNAME}.local:8081/api/status"
echo ""
echo "  4. USB-Stick einstecken (optional, fuer mehr Speicher):"
echo "     -> Wird automatisch nach ${USB_MOUNT} gemountet"
echo "     -> Agent nutzt USB fuer Assets wenn vorhanden"
echo ""
echo "  5. Im VJ-Manager (http://${HEAD_PI_IP}:8080):"
echo "     -> Slave erscheint unter Devices"
echo "     -> Assets per Drag&Drop auf Slave-Monitore ziehen"
echo ""
echo "============================================"
