#!/bin/bash
# =============================================================================
# USB Auto-Mount fuer Displaywall (Head-Pi oder Slave)
# =============================================================================
#
# Richtet automatisches Mounten von USB-Speicher ein.
# Kann einzeln auf dem Head-Pi ausgefuehrt werden
# (auf Slaves wird es durch setup-slave.sh erledigt).
#
# Ausfuehren: sudo ./setup-usb-mount.sh [MOUNT_USER]
# =============================================================================

set -euo pipefail

MOUNT_USER="${1:-head}"
USB_MOUNT="/media/displaywall"

if [ "$(id -u)" -ne 0 ]; then
    echo "Fehler: Als root ausfuehren (sudo)."
    exit 1
fi

echo "[USB-MOUNT] Richte Auto-Mount ein fuer User '${MOUNT_USER}'..."

mkdir -p "${USB_MOUNT}"

# udev-Regel
cat > /etc/udev/rules.d/99-displaywall-usb.rules <<'UDEVEOF'
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", \
  ENV{ID_USB_DRIVER}=="usb-storage", \
  RUN+="/usr/local/bin/displaywall-usb-mount.sh add %k"

ACTION=="remove", SUBSYSTEM=="block", ENV{ID_USB_DRIVER}=="usb-storage", \
  RUN+="/usr/local/bin/displaywall-usb-mount.sh remove %k"
UDEVEOF

# Mount-Skript
cat > /usr/local/bin/displaywall-usb-mount.sh <<MOUNTEOF
#!/bin/bash
USB_MOUNT="${USB_MOUNT}"
ACTION="\$1"
DEVICE="\$2"

if [ "\$ACTION" = "add" ]; then
    mkdir -p "\${USB_MOUNT}"
    if ! mountpoint -q "\${USB_MOUNT}"; then
        mount -o uid=$(id -u ${MOUNT_USER}),gid=$(id -g ${MOUNT_USER}),dmask=022,fmask=133 \
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

udevadm control --reload-rules

echo "[USB-MOUNT] Fertig."
echo "  Mount-Punkt:  ${USB_MOUNT}"
echo "  USB einstecken -> automatisch gemountet"
echo "  Testen: lsblk, mountpoint ${USB_MOUNT}"
