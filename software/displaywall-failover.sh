#!/bin/bash
# displaywall-failover.sh — Admin-AP Failover fuer Slave-Pis
#
# Funktion:
#   - Prueft alle 30s ob das displaywall-WLAN verbunden ist
#   - Nach 3 Minuten ohne Verbindung: AP mit dem Hostnamen aufmachen
#   - Im AP-Modus: weiter scannen, bei Fund von displaywall zurueckwechseln
#
# Installation:
#   sudo cp displaywall-failover.sh /usr/local/bin/
#   sudo chmod +x /usr/local/bin/displaywall-failover.sh
#   sudo cp displaywall-failover.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now displaywall-failover

set -euo pipefail

SSID_TARGET="displaywall"
AP_PASS="12345678"
AP_BAND="bg"
CHECK_INTERVAL=30
FAIL_THRESHOLD=6  # 6 * 30s = 3 Minuten
CON_NAME="netplan-wlan0-displaywall"
AP_CON_NAME="admin-ap"
AP_ADDR="192.168.50.1/24"

HOSTNAME=$(hostname)
AP_SSID="${HOSTNAME}"

fail_count=0
ap_active=false

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

is_connected() {
    # Prueft ob wlan0 mit dem displaywall-SSID verbunden ist
    local current
    current=$(nmcli -t -f GENERAL.CONNECTION dev show wlan0 2>/dev/null | cut -d: -f2)
    [[ "$current" == *"$SSID_TARGET"* ]]
}

displaywall_visible() {
    # Prueft ob displaywall-SSID in Reichweite ist
    nmcli dev wifi rescan 2>/dev/null || true
    sleep 2
    nmcli -t -f SSID dev wifi list 2>/dev/null | grep -q "^${SSID_TARGET}$"
}

start_ap() {
    if $ap_active; then
        return
    fi
    log "Starte Admin-AP: SSID='${AP_SSID}', Pass='${AP_PASS}'"

    # Bestehende AP-Connection loeschen falls vorhanden
    nmcli con delete "$AP_CON_NAME" 2>/dev/null || true

    # AP auf wlan0 starten (gleicher Kanal wie STA, da concurrent mode)
    nmcli con add type wifi ifname wlan0 con-name "$AP_CON_NAME" \
        autoconnect no \
        ssid "$AP_SSID" \
        wifi.mode ap \
        wifi.band "$AP_BAND" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$AP_PASS" \
        ipv4.method shared \
        ipv4.addresses "$AP_ADDR" 2>/dev/null

    nmcli con up "$AP_CON_NAME" 2>/dev/null && {
        ap_active=true
        log "Admin-AP aktiv: ${AP_SSID} (${AP_ADDR})"
    } || {
        log "FEHLER: AP konnte nicht gestartet werden"
    }
}

stop_ap() {
    if ! $ap_active; then
        return
    fi
    log "Stoppe Admin-AP"
    nmcli con down "$AP_CON_NAME" 2>/dev/null || true
    nmcli con delete "$AP_CON_NAME" 2>/dev/null || true
    ap_active=false
}

reconnect_displaywall() {
    log "Verbinde mit ${SSID_TARGET}..."
    stop_ap
    # netplan-Connection reaktivieren
    nmcli con up "$CON_NAME" 2>/dev/null && {
        log "Verbunden mit ${SSID_TARGET}"
        fail_count=0
        return 0
    } || {
        log "Verbindung fehlgeschlagen"
        return 1
    }
}

cleanup() {
    log "Beende..."
    stop_ap
    exit 0
}

trap cleanup SIGTERM SIGINT

log "Displaywall-Failover gestartet (Host: ${HOSTNAME})"
log "Ziel-SSID: ${SSID_TARGET}, AP-SSID: ${AP_SSID}, Threshold: ${FAIL_THRESHOLD}x${CHECK_INTERVAL}s"

while true; do
    if is_connected; then
        if $ap_active; then
            # Wieder verbunden — AP herunterfahren
            stop_ap
        fi
        fail_count=0
    else
        fail_count=$((fail_count + 1))
        log "Nicht verbunden mit ${SSID_TARGET} (${fail_count}/${FAIL_THRESHOLD})"

        if [ $fail_count -ge $FAIL_THRESHOLD ]; then
            if ! $ap_active; then
                start_ap
            else
                # Im AP-Modus: pruefen ob displaywall wieder da
                if displaywall_visible; then
                    log "${SSID_TARGET} wieder sichtbar — wechsle zurueck"
                    reconnect_displaywall || {
                        # Reconnect fehlgeschlagen — AP wieder starten
                        start_ap
                    }
                fi
            fi
        else
            # Noch unter Threshold — versuchen zu reconnecten
            reconnect_displaywall 2>/dev/null || true
        fi
    fi

    sleep $CHECK_INTERVAL
done
