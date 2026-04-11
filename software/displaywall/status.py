"""System-Status: Viewer-Prozesse, Temperatur, Throttle."""

import subprocess


def _run(cmd, timeout=3):
    """Hilfsfunktion: Kommando ausfuehren, stdout zurueckgeben."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def get_status():
    """Aktuellen System-Status abfragen."""
    return {
        "viewer1_running": _run(
            ["docker", "inspect", "-f", "{{.State.Running}}",
             "screenly-anthias-viewer-1"]
        ) == "true",
        "viewer2_running": _run(
            ["systemctl", "is-active", "anthias-viewer2"]
        ) == "active",
        "temperature": _run(["vcgencmd", "measure_temp"]),
    }
