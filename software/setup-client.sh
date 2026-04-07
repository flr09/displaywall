#!/bin/bash

# Headless Setup Script for Client-Pis (Raspberry Pi 5 / Ubuntu 24.04)

echo "========================================"
echo "  Xibo Client-Pi Setup (Headless Mode)  "
echo "========================================"

echo "1. System wird aktualisiert..."
sudo apt-get update && sudo apt-get upgrade -y

echo "2. Xibo Player wird via Snap installiert..."
sudo snap install xibo-player

echo "3. Autostart für Xibo Player wird eingerichtet..."
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

echo "4. Wayland deaktivieren (Erzwingt X11 für bessere Xibo-Kompatibilität)..."
sudo sed -i 's/#WaylandEnable=false/WaylandEnable=false/g' /etc/gdm3/custom.conf

echo "========================================"
echo " Setup abgeschlossen! "
echo "========================================"
echo "Der Pi sollte nun neu gestartet werden."
echo "Befehl: sudo reboot"
echo "Nach dem Neustart öffnet sich der Player auf den Monitoren."
echo "Dort müssen (mit einer kurz angeschlossenen Maus) einmalig CMS-URL und Key eingegeben werden."
