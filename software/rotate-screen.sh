#!/bin/bash

# Helper Script: Bildschirmdrehung für Raspberry Pi OS (Wayland/Wayfire)
# Nutzung: ./rotate-screen.sh [HDMI-A-1|HDMI-A-2] [normal|90|180|270]

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Fehler: Fehlende Parameter."
    echo "Nutzung: $0 <Monitor-Anschluss> <Rotation>"
    echo "Beispiele:"
    echo "  $0 HDMI-A-1 90      (Dreht den ersten Monitor um 90 Grad im Uhrzeigersinn)"
    echo "  $0 HDMI-A-2 270     (Dreht den zweiten Monitor um 270 Grad / Hochkant andersherum)"
    echo "  $0 HDMI-A-1 normal  (Setzt den ersten Monitor zurück auf Querformat)"
    echo ""
    echo "Aktuell erkannte Monitore:"
    wlr-randr | grep "HDMI"
    exit 1
fi

DISPLAY=$1
ROTATION=$2

echo "Drehe Monitor $DISPLAY auf $ROTATION..."
wlr-randr --output "$DISPLAY" --transform "$ROTATION"

echo "Fertig! Die Änderung ist sofort auf dem Bildschirm sichtbar."
echo "Hinweis: Um die Drehung nach einem Neustart dauerhaft zu speichern, nutze das grafische Menü (Screen Configuration) oder trage es in die ~/.config/wayfire.ini ein."
