#!/bin/bash

# Anthias Setup Script für Client-Pis (Slaves)
# Dieses Skript konfiguriert die Locales und startet den Anthias-Installer.

echo "========================================"
echo "  Anthias Client-Pi Setup (Slave)       "
echo "========================================"

if [ "$EUID" -eq 0 ]; then
  echo "FEHLER: Bitte starte dieses Skript NICHT mit sudo!"
  echo "Führe einfach aus: ./setup-client.sh"
  exit
fi

echo "1. System Locales fixen (verhindert Ansible-Abstürze)..."
sudo sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen
sudo sed -i '/en_GB.UTF-8/s/^# //g' /etc/locale.gen
sudo locale-gen
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

echo "2. System-Update (non-interactive)..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update && sudo apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "3. Anthias Installation starten..."
# Startet den offiziellen Installer. Bei Abfragen bitte immer 'Y' wählen.
bash <(curl -sL https://install-anthias.srly.io)

echo "========================================"
echo " Setup abgeschlossen! "
echo " Bitte den Pi mit 'sudo reboot' neu starten."
echo "========================================"
