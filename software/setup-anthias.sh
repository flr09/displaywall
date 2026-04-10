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

echo "Schritt 1.2: Power-Tuning & Auto-Boot (EEPROM & Config)"
# 1. EEPROM: Setze 5A Limit und Auto-Boot bei Stromeingang
sudo rpi-eeprom-config -out current_eeprom.conf
sed -i 's/PSU_MAX_CURRENT=.*/PSU_MAX_CURRENT=5000/g' current_eeprom.conf
if ! grep -q "PSU_MAX_CURRENT" current_eeprom.conf; then echo "PSU_MAX_CURRENT=5000" >> current_eeprom.conf; fi
sed -i 's/POWER_OFF_ON_HALT=.*/POWER_OFF_ON_HALT=0/g' current_eeprom.conf
if ! grep -q "POWER_OFF_ON_HALT" current_eeprom.conf; then echo "POWER_OFF_ON_HALT=0" >> current_eeprom.conf; fi
sudo rpi-eeprom-config --apply current_eeprom.conf
rm current_eeprom.conf

# 2. Config.txt: Bildschirm-Warnungen unterdruecken (Produktion)
#    Im Betrieb duerfen KEINE Overlays auf den Displays erscheinen.
#    Undervoltage-Monitoring laeuft stattdessen ueber monitor-power.sh (Admin per SSH).
sudo sed -i '/avoid_warnings=/d' /boot/firmware/config.txt
sudo sed -i '/usb_max_current_enable=/d' /boot/firmware/config.txt
echo "avoid_warnings=2" | sudo tee -a /boot/firmware/config.txt
# avoid_warnings=2 unterdrueckt das Overlay UND den Blitz komplett.
# usb_max_current_enable wird nicht gesetzt (hat auf dem Pi 5 keinen Effekt).

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
