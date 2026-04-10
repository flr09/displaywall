#!/bin/bash

# Displaywall Testsuite
# Testet Raspberry Pis der Displaywall per SSH von WSL2 aus.
# Usage: displaywall-test.sh [--host <name>] [--all] [--category <cat>] [--verbose]

set -euo pipefail

# === Konfiguration ===

# Alle bekannten Hosts (Name:IP). Erweitern wenn neue Pis dazukommen.
declare -A HOSTS=(
    [head-pi]="192.168.193.105"
    # [pi-links]="<IP>"
    # [pi-mitte]="<IP>"
    # [pi-rechts]="<IP>"
)

SSH_TIMEOUT=5
SSH_OPTS="-o ConnectTimeout=${SSH_TIMEOUT} -o BatchMode=yes -o StrictHostKeyChecking=no"

# === Farben ===

if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' BOLD='' NC=''
fi

# === Zaehler ===

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

# === Hilfsfunktionen ===

pass() {
    ((PASS_COUNT++))
    if [ "$VERBOSE" = true ]; then
        echo -e "  ${GREEN}[PASS]${NC} $1"
    fi
}

fail() {
    ((FAIL_COUNT++))
    echo -e "  ${RED}[FAIL]${NC} $1"
}

warn() {
    ((WARN_COUNT++))
    echo -e "  ${YELLOW}[WARN]${NC} $1"
}

skip() {
    ((SKIP_COUNT++))
    if [ "$VERBOSE" = true ]; then
        echo -e "  ${YELLOW}[SKIP]${NC} $1"
    fi
}

# SSH-Befehl auf Remote-Host ausfuehren
remote() {
    ssh $SSH_OPTS "$CURRENT_HOST" "$@" 2>/dev/null
}

# === Testkategorien ===

test_connectivity() {
    echo -e "\n${BOLD}--- Konnektivitaet ---${NC}"

    local ip="${HOSTS[$CURRENT_HOST]}"

    # Ping
    if ping -c 3 -W 2 "$ip" >/dev/null 2>&1; then
        local avg
        avg=$(ping -c 3 -W 2 "$ip" 2>/dev/null | tail -1 | cut -d'/' -f5)
        if [ -n "$avg" ] && [ "$(echo "$avg < 50" | bc -l 2>/dev/null)" = "1" ]; then
            pass "Ping: ${avg}ms"
        else
            warn "Ping: ${avg}ms (> 50ms)"
        fi
    else
        fail "Ping: Host nicht erreichbar"
        return 1
    fi

    # SSH
    local hostname
    if hostname=$(remote "hostname"); then
        pass "SSH: verbunden (${hostname})"
    else
        fail "SSH: Verbindung fehlgeschlagen"
        return 1
    fi
}

test_hardware() {
    echo -e "\n${BOLD}--- Hardware & Strom ---${NC}"

    # Architektur
    local arch
    arch=$(remote "uname -m")
    if [ "$arch" = "aarch64" ]; then
        pass "Architektur: ${arch}"
    else
        fail "Architektur: ${arch} (erwartet: aarch64)"
    fi

    # Throttle-Status
    local throttled
    throttled=$(remote "vcgencmd get_throttled" | cut -d= -f2)
    if [ "$throttled" = "0x0" ]; then
        pass "Throttle-Status: ${throttled}"
    elif [ "$throttled" = "0x50000" ]; then
        warn "Throttle-Status: ${throttled} (Undervoltage in der Vergangenheit)"
    else
        fail "Throttle-Status: ${throttled} (erwartet: 0x0)"
    fi

    # Spannung
    local volt_raw volt
    volt_raw=$(remote "vcgencmd pmic_read_adc EXT5V_V" 2>/dev/null || echo "")
    if [ -n "$volt_raw" ]; then
        volt=$(echo "$volt_raw" | grep -oP '[0-9]+\.[0-9]+' | head -1)
        if [ -n "$volt" ]; then
            if [ "$(echo "$volt >= 4.63" | bc -l 2>/dev/null)" = "1" ]; then
                pass "Spannung: ${volt}V"
            else
                fail "Spannung: ${volt}V (< 4.63V kritisch!)"
            fi
        else
            skip "Spannung: konnte nicht gelesen werden"
        fi
    else
        skip "Spannung: vcgencmd pmic_read_adc nicht verfuegbar"
    fi

    # Temperatur
    local temp_raw temp
    temp_raw=$(remote "vcgencmd measure_temp")
    temp=$(echo "$temp_raw" | grep -oP '[0-9]+\.[0-9]+')
    if [ -n "$temp" ]; then
        if [ "$(echo "$temp < 80" | bc -l 2>/dev/null)" = "1" ]; then
            pass "Temperatur: ${temp}°C"
        else
            fail "Temperatur: ${temp}°C (>= 80°C!)"
        fi
    else
        skip "Temperatur: konnte nicht gelesen werden"
    fi

    # RAM
    local mem_avail
    mem_avail=$(remote "free -m | awk '/^Mem:/ {print \$7}'")
    if [ -n "$mem_avail" ] && [ "$mem_avail" -gt 500 ] 2>/dev/null; then
        pass "RAM verfuegbar: ${mem_avail}MB"
    elif [ -n "$mem_avail" ]; then
        warn "RAM verfuegbar: ${mem_avail}MB (< 500MB)"
    else
        skip "RAM: konnte nicht gelesen werden"
    fi

    # SD-Karte
    local disk_pct
    disk_pct=$(remote "df / | awk 'NR==2 {print \$5}'" | tr -d '%')
    if [ -n "$disk_pct" ] && [ "$disk_pct" -lt 90 ] 2>/dev/null; then
        pass "SD-Karte: ${disk_pct}% belegt"
    elif [ -n "$disk_pct" ]; then
        fail "SD-Karte: ${disk_pct}% belegt (>= 90%!)"
    else
        skip "SD-Karte: konnte nicht gelesen werden"
    fi
}

test_displays() {
    echo -e "\n${BOLD}--- Displays ---${NC}"

    # HDMI-Status via DRM sysfs (funktioniert immer, kein Wayland noetig)
    for port in 1 2; do
        local status
        status=$(remote "cat /sys/class/drm/card?-HDMI-A-${port}/status 2>/dev/null" || echo "not_found")

        if [ "$status" = "connected" ]; then
            pass "HDMI-${port}: angeschlossen"
        elif [ "$status" = "disconnected" ]; then
            warn "HDMI-${port}: nicht angeschlossen"
        else
            skip "HDMI-${port}: DRM-Status nicht lesbar"
        fi
    done

    # Aufloesung via kmsprint (verfuegbar auf RPi OS) oder Fallback modetest
    local res_tool=""
    if remote "command -v kmsprint" >/dev/null 2>&1; then
        res_tool="kmsprint"
    fi

    if [ "$res_tool" = "kmsprint" ]; then
        local kms_output
        kms_output=$(remote "kmsprint 2>/dev/null" || echo "")

        for port in 1 2; do
            local connector_status
            connector_status=$(remote "cat /sys/class/drm/card?-HDMI-A-${port}/status 2>/dev/null" || echo "")
            if [ "$connector_status" != "connected" ]; then
                skip "HDMI-${port} Aufloesung: nicht angeschlossen"
                continue
            fi

            # Aktive Mode aus kmsprint extrahieren
            local mode
            mode=$(echo "$kms_output" | grep -A5 "HDMI-A-${port}" | grep -oP '[0-9]{3,4}x[0-9]{3,4}' | head -1)

            if [ -n "$mode" ]; then
                if [ "$mode" = "2560x1440" ]; then
                    pass "HDMI-${port} Aufloesung: ${mode}"
                else
                    warn "HDMI-${port} Aufloesung: ${mode} (erwartet: 2560x1440)"
                fi
            else
                skip "HDMI-${port} Aufloesung: konnte nicht ermittelt werden"
            fi
        done
    else
        # Fallback: wlr-randr (braucht Wayland-Session)
        if remote "command -v wlr-randr" >/dev/null 2>&1; then
            local wlr_output
            wlr_output=$(remote "WAYLAND_DISPLAY=wayland-1 wlr-randr 2>/dev/null || WAYLAND_DISPLAY=wayland-0 wlr-randr 2>/dev/null" || echo "")
            if [ -n "$wlr_output" ]; then
                for port in 1 2; do
                    local mode
                    mode=$(echo "$wlr_output" | grep -A3 "HDMI-A-${port}" | grep -oP '[0-9]{3,4}x[0-9]{3,4}' | head -1)
                    if [ -n "$mode" ]; then
                        if [ "$mode" = "2560x1440" ]; then
                            pass "HDMI-${port} Aufloesung: ${mode}"
                        else
                            warn "HDMI-${port} Aufloesung: ${mode} (erwartet: 2560x1440)"
                        fi
                    else
                        skip "HDMI-${port} Aufloesung: konnte nicht ermittelt werden"
                    fi
                done
            else
                skip "Aufloesung: wlr-randr konnte nicht abfragen (kein Wayland-Zugriff via SSH)"
            fi
        else
            skip "Aufloesung: weder kmsprint noch wlr-randr installiert"
        fi
    fi
}

test_services() {
    echo -e "\n${BOLD}--- Services ---${NC}"

    # Docker
    local docker_status
    docker_status=$(remote "systemctl is-active docker 2>/dev/null" || echo "inactive")
    if [ "$docker_status" = "active" ]; then
        pass "Docker: active"
    else
        fail "Docker: ${docker_status}"
    fi

    # Container
    local containers
    containers=$(remote "docker ps --format '{{.Names}}' 2>/dev/null" || echo "")
    if [ -n "$containers" ]; then
        local count
        count=$(echo "$containers" | wc -l)
        pass "Docker-Container: ${count} laufend"
        if [ "$VERBOSE" = true ]; then
            echo "$containers" | while read -r name; do
                echo "         -> ${name}"
            done
        fi
    else
        warn "Docker-Container: keine laufend"
    fi

    # Webinterface
    local http_code
    http_code=$(remote "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:80 2>/dev/null" || echo "000")
    if [ "$http_code" = "200" ]; then
        pass "Webinterface: HTTP ${http_code}"
    elif [ "$http_code" = "000" ]; then
        warn "Webinterface: nicht erreichbar"
    else
        warn "Webinterface: HTTP ${http_code}"
    fi
}

test_config() {
    echo -e "\n${BOLD}--- Konfiguration ---${NC}"

    # avoid_warnings
    local aw_count
    aw_count=$(remote "grep -c 'avoid_warnings=2' /boot/firmware/config.txt 2>/dev/null" || echo "0")
    if [ "$aw_count" -ge 1 ] 2>/dev/null; then
        pass "avoid_warnings=2: gesetzt"
    else
        fail "avoid_warnings=2: nicht gesetzt in /boot/firmware/config.txt"
    fi

    # Zeitzone
    local tz
    tz=$(remote "timedatectl show -p Timezone --value 2>/dev/null" || echo "unbekannt")
    if [ "$tz" = "Europe/Berlin" ]; then
        pass "Zeitzone: ${tz}"
    else
        warn "Zeitzone: ${tz} (erwartet: Europe/Berlin)"
    fi
}

test_network() {
    echo -e "\n${BOLD}--- Netzwerk ---${NC}"

    # Internet (ICMP)
    if remote "ping -c 1 -W 3 8.8.8.8" >/dev/null 2>&1; then
        pass "Internet (ICMP): erreichbar"
    else
        fail "Internet (ICMP): nicht erreichbar"
    fi

    # DNS
    if remote "ping -c 1 -W 3 google.com" >/dev/null 2>&1; then
        pass "DNS: funktioniert"
    else
        fail "DNS: Namensaufloesung fehlgeschlagen"
    fi

    # Andere Pis erreichbar
    for other_host in "${!HOSTS[@]}"; do
        if [ "$other_host" = "$CURRENT_HOST" ]; then
            continue
        fi
        # Nur testen wenn Host konfiguriert (keine Platzhalter-IP)
        local other_ip="${HOSTS[$other_host]}"
        if [[ "$other_ip" == *"<"* ]]; then
            skip "Pi ${other_host}: IP nicht konfiguriert"
            continue
        fi
        if remote "ping -c 1 -W 3 ${other_ip}" >/dev/null 2>&1; then
            pass "Pi ${other_host} (${other_ip}): erreichbar"
        else
            warn "Pi ${other_host} (${other_ip}): nicht erreichbar"
        fi
    done
}

# === Alle Tests fuer einen Host ausfuehren ===

run_tests_for_host() {
    local host="$1"
    CURRENT_HOST="$host"
    local ip="${HOSTS[$host]}"

    echo -e "\n${BOLD}=== Displaywall Testsuite ===${NC}"
    echo -e "Host: ${BOLD}${host}${NC} (${ip})"
    echo -e "Datum: $(date '+%Y-%m-%d %H:%M:%S')"

    PASS_COUNT=0
    FAIL_COUNT=0
    WARN_COUNT=0
    SKIP_COUNT=0

    # Konnektivitaet zuerst — wenn das fehlschlaegt, Rest ueberspringen
    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "connectivity" ]; then
        if ! test_connectivity; then
            echo -e "\n${RED}Abbruch: Host nicht erreichbar.${NC}"
            echo -e "\nErgebnis: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL, ${WARN_COUNT} WARN, ${SKIP_COUNT} SKIP"
            return 1
        fi
    fi

    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "hardware" ]; then
        test_hardware
    fi

    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "displays" ]; then
        test_displays
    fi

    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "services" ]; then
        test_services
    fi

    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "config" ]; then
        test_config
    fi

    if [ -z "$CATEGORY" ] || [ "$CATEGORY" = "network" ]; then
        test_network
    fi

    # Zusammenfassung
    local total=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT + SKIP_COUNT))
    echo -e "\n${BOLD}Ergebnis:${NC} ${GREEN}${PASS_COUNT} PASS${NC}, ${RED}${FAIL_COUNT} FAIL${NC}, ${YELLOW}${WARN_COUNT} WARN${NC}, ${SKIP_COUNT} SKIP (von ${total})"

    if [ "$FAIL_COUNT" -gt 0 ]; then
        return 1
    fi
    return 0
}

# === CLI Argument Parsing ===

VERBOSE=false
CATEGORY=""
TARGET_HOST="head-pi"
RUN_ALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            TARGET_HOST="$2"
            shift 2
            ;;
        --all)
            RUN_ALL=true
            shift
            ;;
        --category)
            CATEGORY="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--host <name>] [--all] [--category <cat>] [--verbose]"
            echo ""
            echo "Optionen:"
            echo "  --host <name>      Einzelnen Host testen (Standard: head-pi)"
            echo "  --all              Alle konfigurierten Hosts testen"
            echo "  --category <cat>   Nur eine Kategorie: connectivity|hardware|displays|services|config|network"
            echo "  --verbose, -v      Auch PASS-Details anzeigen"
            echo "  --help, -h         Diese Hilfe"
            echo ""
            echo "Konfigurierte Hosts:"
            for h in "${!HOSTS[@]}"; do
                echo "  ${h} -> ${HOSTS[$h]}"
            done
            exit 0
            ;;
        *)
            echo "Unbekannte Option: $1 (--help fuer Hilfe)"
            exit 2
            ;;
    esac
done

# Kategorie validieren
if [ -n "$CATEGORY" ]; then
    case "$CATEGORY" in
        connectivity|hardware|displays|services|config|network) ;;
        *)
            echo "Unbekannte Kategorie: $CATEGORY"
            echo "Erlaubt: connectivity, hardware, displays, services, config, network"
            exit 2
            ;;
    esac
fi

# === Hauptprogramm ===

EXIT_CODE=0

if [ "$RUN_ALL" = true ]; then
    for host in "${!HOSTS[@]}"; do
        # Hosts mit Platzhalter-IP ueberspringen
        if [[ "${HOSTS[$host]}" == *"<"* ]]; then
            echo -e "\n${YELLOW}Ueberspringe ${host}: IP nicht konfiguriert${NC}"
            continue
        fi
        run_tests_for_host "$host" || EXIT_CODE=1
    done
else
    if [ -z "${HOSTS[$TARGET_HOST]+x}" ]; then
        echo "Unbekannter Host: $TARGET_HOST"
        echo "Konfigurierte Hosts: ${!HOSTS[*]}"
        exit 2
    fi
    run_tests_for_host "$TARGET_HOST" || EXIT_CODE=1
fi

exit $EXIT_CODE
