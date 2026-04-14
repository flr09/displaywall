#!/usr/bin/env python3
"""Displaywall Watchdog — ueberwacht und repariert kritische Dienste.

Laeuft als systemd-Service, prueft alle 30 Sekunden:
- Anthias Docker-Container (Viewer-1)
- Viewer-2 (systemd)
- Displaywall-Manager (Web-GUI)
- Displaywall-Agent (nur auf Slaves)
- Netzwerk-Konnektivitaet
- apt-daily Timer (muss deaktiviert bleiben)

Bei Problemen: automatischer Neustart + Logging.
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

CHECK_INTERVAL = 30  # Sekunden
MAX_RESTARTS = 5     # pro Dienst pro Stunde
NETWORK_TIMEOUT = 5  # Sekunden

# Home-Verzeichnis: Script liegt in /home/<user>/screenly/
_SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = _SCRIPT_DIR.parent / ".screenly"
LOG_FILE = LOG_DIR / "watchdog.log"

# Zaehler fuer Neustarts: {service_name: [timestamps]}
_restart_history = {}


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Logfile-Rotation: abschneiden wenn >1 MB
    if LOG_FILE.is_file() and LOG_FILE.stat().st_size > 1_000_000:
        lines = LOG_FILE.read_text().splitlines()
        LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_FILE)),
            logging.StreamHandler(),
        ],
    )


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def can_restart(service):
    """Prueft ob wir den Dienst noch neu starten duerfen (max pro Stunde)."""
    now = time.time()
    history = _restart_history.get(service, [])
    # Alte Eintraege entfernen (aelter als 1h)
    history = [t for t in history if now - t < 3600]
    _restart_history[service] = history
    return len(history) < MAX_RESTARTS


def record_restart(service):
    _restart_history.setdefault(service, []).append(time.time())


def is_head():
    """Erkennt ob wir auf dem Head-Pi laufen (Anthias Docker vorhanden)."""
    rc, out, _ = run(["docker", "ps", "--format", "{{.Names}}"], timeout=5)
    return rc == 0 and "screenly" in out


def check_systemd_service(name):
    """Prueft ob ein systemd-Service aktiv ist. Gibt (running, exists) zurueck."""
    rc, out, _ = run(["systemctl", "is-active", name])
    if rc == 0 and out == "active":
        return True, True
    # Pruefen ob Service ueberhaupt existiert
    rc2, _, _ = run(["systemctl", "cat", name])
    return False, rc2 == 0


def check_docker_container(name):
    """Prueft ob ein Docker-Container laeuft."""
    rc, out, _ = run(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return out == "true"


def restart_systemd(name):
    """Startet einen systemd-Service neu."""
    if not can_restart(name):
        logging.error("Max Neustarts erreicht fuer %s — manueller Eingriff noetig", name)
        return False
    logging.warning("Neustart: %s", name)
    rc, _, err = run(["sudo", "systemctl", "restart", name], timeout=30)
    record_restart(name)
    if rc != 0:
        logging.error("Neustart fehlgeschlagen fuer %s: %s", name, err)
        return False
    return True


def restart_docker(name):
    """Startet einen Docker-Container neu."""
    if not can_restart(f"docker:{name}"):
        logging.error("Max Neustarts erreicht fuer Docker %s", name)
        return False
    logging.warning("Docker Neustart: %s", name)
    rc, _, err = run(["docker", "restart", name], timeout=60)
    record_restart(f"docker:{name}")
    if rc != 0:
        logging.error("Docker Neustart fehlgeschlagen fuer %s: %s", name, err)
        return False
    return True


def disable_apt_timers():
    """Stellt sicher, dass apt-daily Timer deaktiviert bleiben."""
    for timer in ["apt-daily.timer", "apt-daily-upgrade.timer"]:
        rc, out, _ = run(["systemctl", "is-active", timer])
        if out == "active":
            logging.warning("Deaktiviere %s (verhindert roten Bildschirm)", timer)
            run(["sudo", "systemctl", "disable", "--now", timer])


def check_network():
    """Prueft Netzwerk-Konnektivitaet (ohne ICMP, da oft geblockt)."""
    import socket
    # Pruefen ob wir eine Route haben
    rc, out, _ = run(["ip", "route", "show", "default"])
    if not out:
        return False
    # TCP-Connect auf DNS-Server als Fallback (ICMP oft geblockt in oeffentl. WLANs)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(NETWORK_TIMEOUT)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except Exception:
        pass
    # Fallback: lokale IP vorhanden?
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip and not ip.startswith("127.")
    except Exception:
        return False


def reconnect_wifi():
    """Versucht WLAN-Interfaces neu zu verbinden."""
    for iface in ["wlan0", "wlan1"]:
        rc, state, _ = run(["nmcli", "-t", "-f", "STATE", "device", "show", iface])
        if "disconnected" in state or "unavailable" in state:
            logging.info("Reconnect %s ...", iface)
            run(["nmcli", "device", "connect", iface], timeout=15)
    # Fallback: kompletter NetworkManager-Restart
    rc, _, _ = run(["nmcli", "general", "status"])
    if rc != 0:
        logging.warning("NetworkManager antwortet nicht — Neustart")
        run(["sudo", "systemctl", "restart", "NetworkManager"], timeout=20)


def write_health_status(checks):
    """Schreibt Health-Status in eine JSON-Datei fuer die Web-GUI."""
    status_file = LOG_DIR / "watchdog_status.json"
    try:
        data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "healthy": all(c["ok"] for c in checks),
            "checks": checks,
        }
        status_file.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def main():
    setup_logging()
    head = is_head()
    role = "head" if head else "slave"
    logging.info("Watchdog gestartet (Rolle: %s, PID: %d)", role, os.getpid())

    while True:
        checks = []

        # --- apt-daily deaktiviert halten ---
        disable_apt_timers()

        # --- Netzwerk ---
        net_ok = check_network()
        checks.append({"name": "network", "ok": net_ok})
        if not net_ok:
            logging.warning("Netzwerk nicht erreichbar — versuche WLAN-Reconnect")
            reconnect_wifi()

        if head:
            # --- Anthias Docker Container ---
            for container in ["screenly-anthias-viewer-1", "screenly-anthias-server-1",
                              "screenly-anthias-websocket-1"]:
                running = check_docker_container(container)
                checks.append({"name": container, "ok": running})
                if not running:
                    logging.warning("Docker Container %s nicht aktiv", container)
                    restart_docker(container)

            # --- Viewer-2 ---
            v2_running, v2_exists = check_systemd_service("anthias-viewer2")
            if v2_exists:
                checks.append({"name": "anthias-viewer2", "ok": v2_running})
                if not v2_running:
                    restart_systemd("anthias-viewer2")

            # --- Displaywall Manager ---
            mgr_running, mgr_exists = check_systemd_service("displaywall-mgr")
            if mgr_exists:
                checks.append({"name": "displaywall-mgr", "ok": mgr_running})
                if not mgr_running:
                    restart_systemd("displaywall-mgr")

        else:
            # --- Slave: Agent ---
            agent_running, agent_exists = check_systemd_service("displaywall-agent")
            if agent_exists:
                checks.append({"name": "displaywall-agent", "ok": agent_running})
                if not agent_running:
                    restart_systemd("displaywall-agent")

        # --- Watchdog-eigener Service (immer pruefen) ---
        # Temperatur-Check: bei >80°C warnen
        try:
            rc, temp_out, _ = run(["vcgencmd", "measure_temp"])
            if temp_out:
                temp_str = temp_out.replace("temp=", "").replace("'C", "")
                temp = float(temp_str)
                checks.append({"name": "temperature", "ok": temp < 80.0, "value": temp})
                if temp >= 80.0:
                    logging.error("Temperatur kritisch: %.1f°C!", temp)
                elif temp >= 70.0:
                    logging.warning("Temperatur hoch: %.1f°C", temp)
        except Exception:
            pass

        write_health_status(checks)

        healthy = all(c["ok"] for c in checks)
        if not healthy:
            failed = [c["name"] for c in checks if not c["ok"]]
            logging.info("Health-Check: FEHLER bei %s", ", ".join(failed))

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
