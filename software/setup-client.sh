#!/bin/bash

# Headless Setup Script for Client-Pis (Raspberry Pi OS 64-bit)

# Setze non-interactive frontend, damit apt-get niemals auf User-Input bei Konfigurations-Dialogen wartet
export DEBIAN_FRONTEND=noninteractive

echo "========================================"
echo "  Xibo Client-Pi Setup (Headless Mode)  "
echo "========================================"

echo "1. System wird aktualisiert..."
# Erzwingt Standard-Antworten
sudo apt-get update && sudo apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "2. Snapd installieren (Wird für Xibo Player auf Raspberry Pi OS benötigt)..."
sudo apt-get install -y snapd
sudo snap install core

echo "3. Xibo Player wird via Snap installiert..."
sudo snap install xibo-player

echo "4. Autostart für Xibo Player wird eingerichtet..."
mkdir -p ~/.config/autostart
cat <<EOF > ~/.config/autostart/xibo-player.desktop
[Desktop Entry]
Type=Application
Exec=xibo-player
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Xibo Player
Comment=Start Xibo Player on Login
EOF

echo "========================================"
echo " Setup abgeschlossen! "
echo "========================================"
echo "Der Pi sollte nun neu gestartet werden."
echo "Befehl: sudo reboot"
echo "Nach dem Neustart öffnet sich der Player auf den Monitoren."
echo "Dort müssen (mit einer kurz angeschlossenen Maus) einmalig CMS-URL und Key eingegeben werden."
