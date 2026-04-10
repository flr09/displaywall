#!/bin/bash

# Power Monitor Tool fuer Raspberry Pi 5
# Loggt Spannung, Strom und Throttle-Status in eine CSV-Datei.
# Nutzung: ./monitor-power.sh [Dauer in Sekunden, Standard: 60]

DURATION=${1:-60}
INTERVAL=2
LOGFILE="$HOME/power-log_$(date +%Y%m%d_%H%M%S).csv"

echo "Timestamp,EXT5V_V,EXT5V_I,Throttled" > "$LOGFILE"
echo "Logging fuer ${DURATION}s alle ${INTERVAL}s nach: $LOGFILE"
echo "Abbrechen mit Strg+C"
echo ""
echo "Timestamp             | Spannung | Strom    | Throttled"
echo "-----------------------+----------+----------+----------"

END=$((SECONDS + DURATION))
while [ $SECONDS -lt $END ]; do
    TS=$(date +"%Y-%m-%d %H:%M:%S")
    VOLT=$(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null | grep -oP '[0-9]+\.[0-9]+')
    AMP=$(vcgencmd pmic_read_adc EXT5V_I 2>/dev/null | grep -oP '[0-9]+\.[0-9]+')
    THROT=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)

    echo "${TS},${VOLT},${AMP},${THROT}" >> "$LOGFILE"

    # Warnung bei kritischen Werten
    WARN=""
    if [ "$(echo "$VOLT < 4.63" | bc -l 2>/dev/null)" = "1" ]; then
        WARN=" << KRITISCH!"
    elif [ "$(echo "$VOLT < 4.80" | bc -l 2>/dev/null)" = "1" ]; then
        WARN=" << niedrig"
    fi

    printf "%s | %8s | %8s | %s%s\n" "$TS" "${VOLT}V" "${AMP}A" "$THROT" "$WARN"
    sleep $INTERVAL
done

echo ""
echo "Fertig. Log gespeichert: $LOGFILE"
echo "Throttle-Flags Erklaerung:"
echo "  0x0     = Alles OK"
echo "  0x50000 = Undervoltage + Throttling (in der Vergangenheit)"
echo "  0x50005 = Undervoltage + Throttling (jetzt aktiv!)"
