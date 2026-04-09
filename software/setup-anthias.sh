#!/bin/bash

# Setup Script for Anthias (Screenly OSE) auf Raspberry Pi OS (Bookworm 64-bit)

echo "=========================================================="
echo " Anthias Installer (Video Wall Player)"
echo "=========================================================="

echo "Schritt 1: System-Update (non-interactive)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update && sudo apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "Schritt 2: Starten der offiziellen Anthias-Installation..."
# Anthias bringt einen eigenen, sehr robusten Installer für Raspberry Pi OS mit
bash <(curl -sL https://install-anthias.srly.io)

echo "=========================================================="
echo " Setup-Befehl abgesetzt! "
echo " WICHTIG: Der Anthias-Installer öffnet evtl. eigene "
echo " Abfragen. Folge den Anweisungen auf dem Bildschirm."
echo " Am Ende musst du den Pi neu starten (sudo reboot)."
echo "=========================================================="
