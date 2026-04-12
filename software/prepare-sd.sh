#!/bin/bash
# =============================================================================
# SD-Karte fuer Displaywall Slave vorbereiten
# =============================================================================
#
# Ausfuehren NACH dem Flashen mit Pi Imager.
# SD-Karte nochmal einlegen, dann:
#
#   ./prepare-sd.sh slave1 [/media/$USER/bootfs] [/media/$USER/rootfs]
#
# Pi Imager Einstellungen:
#   - OS: Raspberry Pi OS (64-bit, Lite genuegt)
#   - Hostname: <wird von diesem Skript ueberschrieben>
#   - SSH aktivieren: Ja (Passwort-Auth)
#   - Benutzer: head / <Passwort>
#   - WLAN: SSID + Passwort eintragen
#   - Locale: de_DE.UTF-8, Europe/Berlin
# =============================================================================

set -euo pipefail

SLAVE_NAME="${1:-}"
BOOT_PART="${2:-}"
ROOT_PART="${3:-}"

if [ -z "$SLAVE_NAME" ]; then
    echo "Verwendung: $0 <slave-name> [boot-partition] [root-partition]"
    echo ""
    echo "Beispiel:   $0 slave1"
    echo "            $0 slave1 /media/chris/bootfs /media/chris/rootfs"
    echo ""
    echo "Wenn keine Partitionen angegeben werden, wird automatisch gesucht."
    exit 1
fi

# --- Partitionen finden ---

if [ -z "$BOOT_PART" ]; then
    # Typische Mount-Punkte unter Linux
    for candidate in \
        "/media/$USER/bootfs" \
        "/media/$USER/boot" \
        "/media/$USER/BOOT" \
        "/run/media/$USER/bootfs" \
        "/mnt/bootfs"; do
        if [ -d "$candidate" ] && [ -f "$candidate/cmdline.txt" ]; then
            BOOT_PART="$candidate"
            break
        fi
    done
fi

if [ -z "$ROOT_PART" ]; then
    for candidate in \
        "/media/$USER/rootfs" \
        "/media/$USER/root" \
        "/run/media/$USER/rootfs" \
        "/mnt/rootfs"; do
        if [ -d "$candidate" ] && [ -d "$candidate/etc/systemd" ]; then
            ROOT_PART="$candidate"
            break
        fi
    done
fi

if [ -z "$BOOT_PART" ]; then
    echo "FEHLER: Boot-Partition nicht gefunden."
    echo "SD-Karte einlegen und Pfad manuell angeben."
    exit 1
fi

if [ -z "$ROOT_PART" ]; then
    echo "FEHLER: Root-Partition nicht gefunden."
    echo "SD-Karte einlegen und Pfad manuell angeben."
    exit 1
fi

echo "Boot-Partition: $BOOT_PART"
echo "Root-Partition: $ROOT_PART"
echo "Slave-Name:     $SLAVE_NAME"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 1. Konfigurationsdatei ---

echo "[1/4] Schreibe displaywall.conf..."
cat > "${BOOT_PART}/displaywall.conf" <<EOF
SLAVE_HOSTNAME="${SLAVE_NAME}"
HEAD_PI_IP="192.168.193.105"
HEAD_PI_PORT="8080"
SLAVE_USER="head"
HDMI1_ROTATION="0"
HDMI2_ROTATION="0"
RESOLUTION="2560x1440"
EOF

# --- 2. Firstboot-Skript ---

echo "[2/4] Kopiere firstboot-displaywall.sh..."
cp "${SCRIPT_DIR}/firstboot-displaywall.sh" "${BOOT_PART}/firstboot-displaywall.sh"
chmod +x "${BOOT_PART}/firstboot-displaywall.sh"

# --- 3. Systemd-Service ---

echo "[3/4] Installiere Firstboot-Service..."
sudo cp "${SCRIPT_DIR}/displaywall-firstboot.service" \
    "${ROOT_PART}/etc/systemd/system/displaywall-firstboot.service"

sudo ln -sf /etc/systemd/system/displaywall-firstboot.service \
    "${ROOT_PART}/etc/systemd/system/multi-user.target.wants/displaywall-firstboot.service"

# --- 4. Verifikation ---

echo "[4/4] Verifikation..."
echo ""

OK=true
[ -f "${BOOT_PART}/displaywall.conf" ] && echo "  ✓ displaywall.conf" || { echo "  ✗ displaywall.conf"; OK=false; }
[ -f "${BOOT_PART}/firstboot-displaywall.sh" ] && echo "  ✓ firstboot-displaywall.sh" || { echo "  ✗ firstboot-displaywall.sh"; OK=false; }
[ -f "${ROOT_PART}/etc/systemd/system/displaywall-firstboot.service" ] && echo "  ✓ displaywall-firstboot.service" || { echo "  ✗ displaywall-firstboot.service"; OK=false; }
[ -L "${ROOT_PART}/etc/systemd/system/multi-user.target.wants/displaywall-firstboot.service" ] && echo "  ✓ Service-Symlink" || { echo "  ✗ Service-Symlink"; OK=false; }

echo ""
if $OK; then
    echo "SD-Karte bereit fuer ${SLAVE_NAME}!"
    echo ""
    echo "Naechste Schritte:"
    echo "  1. SD-Karte auswerfen"
    echo "  2. In Slave-Pi einlegen"
    echo "  3. LAN-Kabel an Head-Pi/Switch anschliessen"
    echo "  4. Strom an — Slave konfiguriert sich selbst"
    echo "  5. Nach ca. 5 Min: curl http://${SLAVE_NAME}.local:8081/api/status"
else
    echo "FEHLER: Nicht alle Dateien korrekt kopiert!"
fi
