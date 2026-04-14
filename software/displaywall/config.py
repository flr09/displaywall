"""Zentrale Konfiguration fuer alle Displaywall-Komponenten.

Pfade, Konstanten und Display-Konfiguration (displays.json).
"""

import json
from pathlib import Path

# --- Pfade ---

HOME = Path.home()
SCREENLY_DIR = HOME / ".screenly"
DB_PATH = SCREENLY_DIR / "screenly.db"
DW_DB_PATH = SCREENLY_DIR / "displaywall.db"
DISPLAYS_JSON = SCREENLY_DIR / "displays.json"
ASSET_DIR = HOME / "screenly_assets"

# --- Konstanten ---

# Prefix im Asset-Namen fuer Display-Zuweisung
DISPLAY_PREFIX = "2:"

# Docker mountet Assets unter /data, auf dem Host unter $HOME
DOCKER_DATA_PREFIX = "/data/"
HOST_DATA_PREFIX = str(HOME) + "/"

# DRM/Display
CONNECTOR_1 = "HDMI-A-1"
CONNECTOR_2 = "HDMI-A-2"

# Netzwerk
WEBUI_PORT = 8080
ANTHIAS_PORT = 80


# --- Display-Konfiguration (displays.json) ---

_DEFAULT_DISPLAYS = {
    CONNECTOR_1: {"rotation": 0, "resolution": "2560x1440"},
    CONNECTOR_2: {"rotation": 0, "resolution": "2560x1440"},
}


def load_displays():
    """Liest Display-Konfiguration. Legt Default an falls nicht vorhanden."""
    try:
        with open(DISPLAYS_JSON) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_displays(_DEFAULT_DISPLAYS)
        return _DEFAULT_DISPLAYS.copy()


def save_displays(data):
    """Speichert Display-Konfiguration."""
    DISPLAYS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DISPLAYS_JSON, "w") as f:
        json.dump(data, f, indent=2)


def resolve_uri(uri):
    """Docker-Pfade (/data/...) auf Host-Pfade (/home/head/...) umschreiben."""
    if uri.startswith(DOCKER_DATA_PREFIX):
        return HOST_DATA_PREFIX + uri[len(DOCKER_DATA_PREFIX):]
    return uri
