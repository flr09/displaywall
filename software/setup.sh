#!/bin/bash

# Setup Script for Monitorwall (Raspberry Pi OS 64-bit)
# Setze non-interactive frontend, damit apt-get niemals auf User-Input bei Konfigurations-Dialogen wartet
export DEBIAN_FRONTEND=noninteractive

echo "--- 1. System Update ---"
# -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" erzwingt Standard-Antworten
sudo apt-get update && sudo apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "--- 2. Installing Docker & Docker-Compose ---"
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm get-docker.sh

echo "--- 3. Installing Snapd (Required for Xibo Player) ---"
sudo apt-get install -y snapd
sudo snap install core

echo "--- 4. Installing Xibo Player ---"
sudo snap install xibo-player

echo "======================================================="
echo " Setup fast abgeschlossen! "
echo " WICHTIG: Du musst den Pi jetzt einmal neu starten, "
echo " damit Docker und Snap korrekt geladen werden."
echo " Befehl: sudo reboot"
echo "======================================================="
echo " Danach kannst du das CMS starten mit:"
echo " cd ~/software/xibo-docker-*"
echo " sudo docker compose up -d"
