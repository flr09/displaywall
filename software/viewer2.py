#!/usr/bin/env python3
"""Standalone Viewer fuer HDMI-A-2 (Display 2).

Liest die Anthias-SQLite-Datenbank, filtert Assets mit Prefix '2:',
und spielt sie ueber mpv mit --vo=drm --drm-connector=HDMI-A-2 ab.
Laeuft als systemd-Service auf CPU-Kernen 2-3.
"""

import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Konfiguration
DB_PATH = Path.home() / ".screenly" / "screenly.db"
DISPLAYS_JSON = Path.home() / ".screenly" / "displays.json"
ASSET_DIR = Path.home() / "screenly_assets"
# Docker-Container mounten Assets unter /data, auf dem Host liegen sie unter $HOME
DOCKER_DATA_PREFIX = "/data/"
HOST_DATA_PREFIX = str(Path.home()) + "/"
PREFIX = "2:"
CONNECTOR = "HDMI-A-2"
EMPTY_PLAYLIST_DELAY = 5
DRM_CARD = "/dev/dri/card1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [viewer2] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

current_process = None


def signal_handler(sig, frame):
    """Sauberes Beenden bei SIGTERM/SIGINT."""
    logging.info("Signal %s empfangen, beende...", sig)
    if current_process and current_process.poll() is None:
        current_process.terminate()
        try:
            current_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_process.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def load_rotation():
    """Liest Rotation fuer HDMI-A-2 aus displays.json."""
    try:
        with open(DISPLAYS_JSON) as f:
            config = json.load(f)
        return config.get(CONNECTOR, {}).get("rotation", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def get_db_mtime():
    """Aenderungszeitpunkt der Datenbank."""
    try:
        return os.path.getmtime(DB_PATH)
    except OSError:
        return 0


def load_playlist():
    """Liest aktive Assets mit Prefix '2:' aus der Anthias-DB."""
    if not DB_PATH.exists():
        logging.warning("Datenbank nicht gefunden: %s", DB_PATH)
        return []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT name, uri, mimetype, duration, play_order
            FROM assets
            WHERE is_enabled = 1
              AND is_processing = 0
              AND name LIKE ?
              AND start_date <= ?
              AND end_date >= ?
            ORDER BY play_order ASC
            """,
            (f"{PREFIX}%", now, now),
        )
        assets = [dict(row) for row in cursor.fetchall()]
        conn.close()
    except sqlite3.Error as e:
        logging.error("DB-Fehler: %s", e)
        return []

    logging.info("Playlist geladen: %d Assets", len(assets))
    for a in assets:
        logging.debug("  %s (%s, %ss)", a["name"], a["mimetype"], a["duration"])

    return assets


def resolve_uri(uri):
    """Docker-Pfade (/data/...) auf Host-Pfade umschreiben."""
    if uri.startswith(DOCKER_DATA_PREFIX):
        return HOST_DATA_PREFIX + uri[len(DOCKER_DATA_PREFIX):]
    return uri


def play_asset(asset, rotation):
    """Spielt ein Asset ueber mpv auf HDMI-A-2."""
    global current_process

    uri = resolve_uri(asset["uri"])
    mime = asset["mimetype"]
    duration = max(int(float(asset["duration"])), 1)
    display_name = asset["name"][len(PREFIX):]  # Prefix entfernen fuer Log

    cmd = [
        "mpv",
        "--no-terminal",
        "--vo=gpu",
        "--gpu-context=drm",
        f"--drm-connector={CONNECTOR}",
    ]

    if rotation:
        cmd.append(f"--video-rotate={rotation}")

    if "image" in mime:
        cmd.extend([
            f"--image-display-duration={duration}",
            "--loop-file=no",
        ])
        logging.info("Bild: %s (%ds)", display_name, duration)
    elif "video" in mime:
        logging.info("Video: %s", display_name)
    else:
        logging.warning("Unbekannter Typ: %s (%s), ueberspringe", display_name, mime)
        return

    cmd.append("--")
    cmd.append(uri)

    try:
        start = time.monotonic()
        logging.debug("mpv cmd: %s", " ".join(cmd))
        current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        current_process.wait()
        elapsed = time.monotonic() - start
        # Wenn mpv in < 2s beendet, ist vermutlich ein Fehler aufgetreten
        if elapsed < 2:
            output = current_process.stdout.read().decode(errors="replace").strip()
            if output:
                logging.warning("mpv output: %s", output[:500])
            logging.warning("mpv beendete nach %.1fs, warte 3s...", elapsed)
            time.sleep(3)
    except Exception as e:
        logging.error("mpv-Fehler: %s", e)
        time.sleep(3)
    finally:
        current_process = None


def clear_screen():
    """HDMI-A-2 schwarz schalten (kurzer mpv mit leerem Bild)."""
    # Einfachste Methode: nichts tun, mpv raeumt selbst auf
    pass


def main():
    logging.info("Viewer-2 gestartet (Connector: %s, Prefix: %s)", CONNECTOR, PREFIX)

    last_mtime = 0
    playlist = []
    index = 0

    while True:
        # Playlist neu laden wenn DB sich geaendert hat
        mtime = get_db_mtime()
        if mtime != last_mtime:
            last_mtime = mtime
            playlist = load_playlist()
            if playlist:
                index = index % len(playlist)
            else:
                index = 0

        if not playlist:
            logging.debug("Playlist leer, warte %ds...", EMPTY_PLAYLIST_DELAY)
            time.sleep(EMPTY_PLAYLIST_DELAY)
            continue

        rotation = load_rotation()
        asset = playlist[index]
        play_asset(asset, rotation)
        index = (index + 1) % len(playlist)


if __name__ == "__main__":
    main()
