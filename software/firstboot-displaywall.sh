#!/bin/bash
# =============================================================================
# Displaywall Slave — Firstboot-Provisioning
# =============================================================================
#
# Dieses Skript wird beim ersten Boot des Slave-Pi ausgefuehrt.
# Es kontaktiert den Head-Pi, laedt das Setup herunter und fuehrt es aus.
#
# Installation auf SD-Karte:
#   Nach dem Flashen mit Pi Imager die SD-Karte nochmal einlegen und:
#
#   1. Skript auf die Boot-Partition kopieren:
#      cp firstboot-displaywall.sh /boot/firmware/
#
#   2. Systemd-Service auf die Root-Partition kopieren:
#      sudo cp displaywall-firstboot.service \
#           /media/$USER/rootfs/etc/systemd/system/
#      sudo ln -s /etc/systemd/system/displaywall-firstboot.service \
#           /media/$USER/rootfs/etc/systemd/system/multi-user.target.wants/
#
#   Oder einfacher — nach erstem SSH-Zugang:
#      ssh head@<slave-ip> "curl -sL http://head-pi:8080/api/provision/setup | sudo bash"
#
# Konfiguration: Die Datei /boot/firmware/displaywall.conf wird gelesen.
# =============================================================================

set -euo pipefail

LOG="/var/log/displaywall-firstboot.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Displaywall Firstboot: $(date) ==="

# --- Konfiguration laden ---

CONF="/boot/firmware/displaywall.conf"
if [ -f "$CONF" ]; then
    source "$CONF"
    echo "Konfiguration geladen aus $CONF"
else
    echo "WARNUNG: $CONF nicht gefunden, nutze Defaults."
fi

# Defaults (werden von displaywall.conf ueberschrieben wenn vorhanden)
SLAVE_HOSTNAME="${SLAVE_HOSTNAME:-$(hostname)}"
HEAD_PI_IP="${HEAD_PI_IP:-head-pi}"
HEAD_PI_PORT="${HEAD_PI_PORT:-8080}"
SLAVE_USER="${SLAVE_USER:-head}"
HDMI1_ROTATION="${HDMI1_ROTATION:-0}"
HDMI2_ROTATION="${HDMI2_ROTATION:-0}"
RESOLUTION="${RESOLUTION:-2560x1440}"

HEAD_URL="http://${HEAD_PI_IP}:${HEAD_PI_PORT}"

echo "Slave:   ${SLAVE_HOSTNAME}"
echo "Head-Pi: ${HEAD_URL}"

# --- Netzwerk abwarten ---

echo "Warte auf Netzwerk..."
MAX_WAIT=120
WAITED=0
while ! ping -c1 -W2 "${HEAD_PI_IP}" &>/dev/null; do
    sleep 3
    WAITED=$((WAITED + 3))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "FEHLER: Head-Pi nicht erreichbar nach ${MAX_WAIT}s."
        echo "Netzwerk-Status:"
        ip addr show
        echo "Breche ab. Manuelles Setup noetig."
        exit 1
    fi
done
echo "Head-Pi erreichbar nach ${WAITED}s."

# --- Provision-Info abrufen ---

echo "Rufe Provisioning-Info ab..."
PROVISION_INFO=$(curl -sL "${HEAD_URL}/api/provision" 2>/dev/null || true)
if [ -z "$PROVISION_INFO" ]; then
    echo "FEHLER: Konnte Provision-Info nicht abrufen."
    echo "Versuche direkten Download..."
fi

# --- Setup-Skript und Agent herunterladen ---

WORK_DIR="/tmp/displaywall-setup"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "Lade setup-slave.sh..."
curl -sL "${HEAD_URL}/api/provision/setup" -o setup-slave.sh
if [ ! -s setup-slave.sh ]; then
    echo "FEHLER: setup-slave.sh leer oder nicht heruntergeladen."
    exit 1
fi

echo "Lade displaywall-agent.py..."
curl -sL "${HEAD_URL}/api/provision/agent" -o displaywall-agent.py
if [ ! -s displaywall-agent.py ]; then
    echo "FEHLER: displaywall-agent.py leer oder nicht heruntergeladen."
    exit 1
fi

echo "Downloads OK ($(wc -c < setup-slave.sh) + $(wc -c < displaywall-agent.py) Bytes)"

# --- Setup ausfuehren ---

echo "Starte Setup..."
export SLAVE_HOSTNAME HEAD_PI_IP SLAVE_USER HDMI1_ROTATION HDMI2_ROTATION RESOLUTION
chmod +x setup-slave.sh
bash setup-slave.sh

# --- Firstboot deaktivieren (einmalig) ---

echo "Deaktiviere Firstboot-Service..."
systemctl disable displaywall-firstboot.service 2>/dev/null || true
rm -f /etc/systemd/system/displaywall-firstboot.service
rm -f /etc/systemd/system/multi-user.target.wants/displaywall-firstboot.service

# --- Marker setzen ---

touch /home/${SLAVE_USER}/.displaywall/provisioned
echo "${SLAVE_HOSTNAME}" > /home/${SLAVE_USER}/.displaywall/provisioned
chown "${SLAVE_USER}:${SLAVE_USER}" /home/${SLAVE_USER}/.displaywall/provisioned

echo ""
echo "=== Firstboot abgeschlossen: $(date) ==="
echo "=== REBOOT in 10 Sekunden ==="
sleep 10
reboot
