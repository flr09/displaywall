#!/usr/bin/env python3
"""Standalone Viewer fuer HDMI-A-2 (Display 2).

Liest die Anthias-SQLite-Datenbank, filtert Assets mit Prefix '2:',
und spielt sie ueber mpv mit --vo=gpu --gpu-context=drm ab.
Laeuft als systemd-Service auf CPU-Kernen 2-3.
"""

import logging
import signal
import subprocess
import sys
import time

from displaywall.config import (
    CONNECTOR_2,
    DISPLAY_PREFIX,
    load_displays,
    resolve_uri,
)
from displaywall.db import get_db_mtime, get_playlist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [viewer2] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

EMPTY_PLAYLIST_DELAY = 5
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


def get_rotation():
    """Rotation fuer HDMI-A-2 aus displays.json lesen."""
    displays = load_displays()
    return displays.get(CONNECTOR_2, {}).get("rotation", 0)


def play_asset(asset, rotation):
    """Spielt ein Asset ueber mpv auf HDMI-A-2."""
    global current_process

    uri = resolve_uri(asset["uri"])
    mime = asset["mimetype"]
    duration = max(int(float(asset["duration"])), 1)
    display_name = asset["name"][len(DISPLAY_PREFIX):]

    cmd = [
        "mpv",
        "--no-terminal",
        "--vo=gpu",
        "--gpu-context=drm",
        f"--drm-connector={CONNECTOR_2}",
    ]

    if rotation:
        cmd.append(f"--video-rotate={rotation}")

    if "image" in mime:
        cmd.extend([f"--image-display-duration={duration}", "--loop-file=no"])
        logging.info("Bild: %s (%ds)", display_name, duration)
    elif "video" in mime:
        logging.info("Video: %s", display_name)
    else:
        logging.warning("Unbekannter Typ: %s (%s), ueberspringe", display_name, mime)
        return

    cmd.extend(["--", uri])

    try:
        start = time.monotonic()
        current_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        current_process.wait()
        elapsed = time.monotonic() - start

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


def main():
    logging.info("Viewer-2 gestartet (Connector: %s, Prefix: %s)", CONNECTOR_2, DISPLAY_PREFIX)

    last_mtime = 0
    playlist = []
    index = 0

    while True:
        mtime = get_db_mtime()
        if mtime != last_mtime:
            last_mtime = mtime
            playlist = get_playlist(DISPLAY_PREFIX)
            logging.info("Playlist geladen: %d Assets", len(playlist))
            index = index % len(playlist) if playlist else 0

        if not playlist:
            logging.debug("Playlist leer, warte %ds...", EMPTY_PLAYLIST_DELAY)
            time.sleep(EMPTY_PLAYLIST_DELAY)
            continue

        rotation = get_rotation()
        play_asset(playlist[index], rotation)
        index = (index + 1) % len(playlist)


if __name__ == "__main__":
    main()
