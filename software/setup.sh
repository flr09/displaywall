#!/bin/bash

# Setup Script for Monitorwall (Raspberry Pi 5 / Ubuntu 24.04)

echo "--- Installing Docker & Docker-Compose ---"
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "--- Installing Xibo Player via Snap ---"
sudo snap install xibo-player

echo "--- Xibo CMS (Docker) Setup ---"
echo "To start Xibo CMS, go to the xibo-docker folder and run: docker compose up -d"
echo "Note: Edit config.env before starting (copy from config.env.template)"

echo "--- System Optimizations ---"
echo "Don't forget to set 'Auto-Login' in Ubuntu Settings and switch to 'X11' if necessary for hardware acceleration."
