#!/bin/bash

# Setup Script for Anthias (Screenly OSE) auf Raspberry Pi OS (Bookworm 64-bit)

echo "=========================================================="
echo " Anthias Installer (Video Wall Player)"
echo "=========================================================="

if [ "$EUID" -eq 0 ]; then
  echo "FEHLER: Bitte starte dieses Skript NICHT mit sudo!"
  echo "Führe einfach aus: ./setup-anthias.sh"
  exit
fi

echo "Schritt 1: System-Update (non-interactive)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update && sudo apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "Schritt 1.5: Fix System Locales (verhindert Ansible Abstürze)"
sudo sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen
sudo sed -i '/en_GB.UTF-8/s/^# //g' /etc/locale.gen
sudo locale-gen
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

echo "Schritt 2: Starten der offiziellen Anthias-Installation..."
# Anthias bringt einen eigenen, sehr robusten Installer für Raspberry Pi OS mit. Darf nicht als Root laufen!
bash <(curl -sL https://install-anthias.srly.io)

echo "=========================================================="
echo " Setup-Befehl abgesetzt! "
echo " WICHTIG: Der Anthias-Installer öffnet evtl. eigene "
echo " Abfragen. Folge den Anweisungen auf dem Bildschirm."
echo " Am Ende musst du den Pi neu starten (sudo reboot)."
echo "=========================================================="
