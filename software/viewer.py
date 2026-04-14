#!/usr/bin/env python3
"""Displaywall Viewer — steuert BEIDE HDMI-Ausgaenge via mpv IPC.

Startet zwei persistente mpv-Prozesse (einen pro Display) und steuert sie
per JSON IPC. Ein einzelner Prozess verhindert DRM-Konflikte, da die
mpv-Instanzen nacheinander (nicht gleichzeitig) gestartet werden.

Aufruf: viewer.py [--displays head-1:HDMI-A-1,head-2:HDMI-A-2]
"""

import argparse
import json
import logging
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from displaywall.config import load_displays, resolve_uri, DISPLAYS_JSON
from displaywall.wall import load_wall_config, WALL_CONFIG

PLAYBACK_STATE_FILE = Path(__file__).parent / "displaywall" / "playback_state.json"
COMMAND_FILE = Path(__file__).parent / "displaywall" / "viewer_cmd.json"
MPV_STARTUP_TIMEOUT = 10
EMPTY_PLAYLIST_DELAY = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [viewer] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def write_playback_state(states):
    """Schreibt Playback-State aller Displays."""
    try:
        PLAYBACK_STATE_FILE.write_text(json.dumps(states))
    except Exception:
        pass


class MpvInstance:
    """Ein persistenter mpv-Prozess fuer einen HDMI-Ausgang."""

    def __init__(self, monitor_id, connector, rotation, sock_path):
        self.monitor_id = monitor_id
        self.connector = connector
        self.rotation = rotation
        self.sock_path = sock_path
        self.process = None
        self.current_uri = None
        self.index = 0

    def start(self):
        """mpv im Idle-Modus starten."""
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass

        # Wayland-Modus (unter labwc) oder DRM-Fallback
        wayland = os.environ.get("WAYLAND_DISPLAY")

        cmd = ["mpv", "--no-terminal"]

        if wayland:
            cmd += [
                "--vo=gpu",
                "--gpu-context=wayland",
                "--fullscreen",
                f"--fs-screen-name={self.connector}",
            ]
        else:
            cmd += [
                "--vo=gpu",
                "--gpu-context=drm",
                f"--drm-connector={self.connector}",
            ]

        cmd += [
            f"--input-ipc-server={self.sock_path}",
            "--idle=yes",
            "--keep-open=yes",
            "--image-display-duration=inf",
            "--cursor-autohide=always",
            "--background=none",
            "--force-window=yes",
        ]

        if self.rotation:
            cmd.append(f"--video-rotate={self.rotation}")

        logging.info("[%s] Starte mpv auf %s (Rotation: %d)",
                     self.monitor_id, self.connector, self.rotation)

        self.process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Warten bis Socket bereit
        for _ in range(MPV_STARTUP_TIMEOUT * 10):
            if Path(self.sock_path).exists():
                time.sleep(0.3)
                return True
            time.sleep(0.1)

        logging.error("[%s] mpv-Socket nicht bereit", self.monitor_id)
        return False

    def _ipc_send(self, command):
        """IPC-Befehl senden und Antwort lesen."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(self.sock_path)
            payload = json.dumps({"command": command}) + "\n"
            sock.sendall(payload.encode())
            sock.settimeout(1)
            try:
                sock.recv(4096)
            except socket.timeout:
                pass
            sock.close()
            return True
        except Exception as e:
            logging.warning("[%s] IPC-Fehler: %s", self.monitor_id, e)
            return False

    def load_file(self, uri):
        """Datei laden per IPC."""
        ok = self._ipc_send(["loadfile", uri, "replace"])
        if ok:
            self.current_uri = uri
        return ok

    def set_rotation(self, rotation):
        """Rotation live per IPC aendern."""
        if rotation != self.rotation:
            logging.info("[%s] Rotation: %d -> %d", self.monitor_id, self.rotation, rotation)
            self._ipc_send(["set_property", "video-rotate", rotation])
            self.rotation = rotation

    def is_alive(self):
        return self.process and self.process.poll() is None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--displays",
        default="head-1:HDMI-A-1,head-2:HDMI-A-2",
        help="Komma-getrennte Liste von monitor_id:connector Paaren",
    )
    args = parser.parse_args()

    # Displays parsen
    display_list = []
    for pair in args.displays.split(","):
        parts = pair.strip().split(":")
        if len(parts) == 2:
            display_list.append({"id": parts[0], "connector": parts[1]})

    if not display_list:
        logging.error("Keine Displays konfiguriert")
        sys.exit(1)

    # Signal-Handler
    instances = []

    def handle_signal(sig, frame):
        logging.info("Signal %s — beende alle mpv-Instanzen...", sig)
        for inst in instances:
            inst.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Rotation aus displays.json lesen
    disp_config = load_displays()

    # mpv-Instanzen starten (nacheinander, mit Pause dazwischen)
    for d in display_list:
        rotation = disp_config.get(d["connector"], {}).get("rotation", 0)
        sock = f"/tmp/mpv-{d['id']}.sock"
        inst = MpvInstance(d["id"], d["connector"], rotation, sock)
        if inst.start():
            instances.append(inst)
            logging.info("[%s] mpv laeuft", d["id"])
        else:
            logging.error("[%s] mpv-Start fehlgeschlagen", d["id"])
        time.sleep(2)  # Pause zwischen Starts

    if not instances:
        logging.error("Keine mpv-Instanz gestartet")
        sys.exit(1)

    logging.info("%d Display(s) aktiv", len(instances))

    # Playback-Loop — Masterclock-Sync
    last_wall_mtime = 0
    last_disp_mtime = 0
    playlists = {}
    playback_state = {}
    next_change = {}    # monitor_id -> wall-clock epoch fuer naechsten Wechsel

    # Alle Displays starten sofort
    for inst in instances:
        next_change[inst.monitor_id] = 0

    while True:
        now = time.time()

        # Abgestuerzte mpv-Instanzen neu starten
        for inst in instances:
            if not inst.is_alive():
                logging.warning("[%s] mpv abgestuerzt — Neustart", inst.monitor_id)
                disp_config = load_displays()
                rotation = disp_config.get(inst.connector, {}).get("rotation", 0)
                inst.rotation = rotation
                inst.start()
                inst.current_uri = None
                next_change[inst.monitor_id] = 0

        # Rotation-Aenderungen aus displays.json live anwenden
        try:
            disp_mtime = DISPLAYS_JSON.stat().st_mtime
        except OSError:
            disp_mtime = 0

        if disp_mtime != last_disp_mtime:
            last_disp_mtime = disp_mtime
            disp_config = load_displays()
            for inst in instances:
                new_rot = disp_config.get(inst.connector, {}).get("rotation", 0)
                inst.set_rotation(new_rot)

        # Playlist aus wall_config.json (Change Detection)
        try:
            wall_mtime = WALL_CONFIG.stat().st_mtime
        except OSError:
            wall_mtime = 0

        if wall_mtime != last_wall_mtime:
            last_wall_mtime = wall_mtime
            wc = load_wall_config()
            for inst in instances:
                old_pl = playlists.get(inst.monitor_id, [])
                new_pl = wc.get("playlists", {}).get(inst.monitor_id, [])
                playlists[inst.monitor_id] = new_pl
                if len(new_pl) != len(old_pl):
                    logging.info("[%s] Playlist: %d Assets", inst.monitor_id, len(new_pl))
                if new_pl and inst.index >= len(new_pl):
                    inst.index = 0

        # Externe Befehle verarbeiten (next/prev aus Web-GUI)
        if COMMAND_FILE.exists():
            try:
                cmds = json.loads(COMMAND_FILE.read_text())
                COMMAND_FILE.unlink()
                if not isinstance(cmds, list):
                    cmds = [cmds]
                for cmd in cmds:
                    action = cmd.get("cmd", "")
                    target = cmd.get("monitor", "")
                    for inst in instances:
                        if target and inst.monitor_id != target:
                            continue
                        pl = playlists.get(inst.monitor_id, [])
                        if not pl:
                            continue
                        if action == "next":
                            # Sofort naechstes Bild
                            next_change[inst.monitor_id] = 0
                        elif action == "prev":
                            inst.index = (inst.index - 2) % len(pl)
                            next_change[inst.monitor_id] = 0
                        logging.info("[%s] Befehl: %s", inst.monitor_id, action)
            except Exception as e:
                logging.warning("Command-Datei Fehler: %s", e)

        # Fuer jedes Display pruefen ob Wechsel faellig
        pending_switches = []
        for inst in instances:
            if now < next_change.get(inst.monitor_id, 0):
                continue

            pl = playlists.get(inst.monitor_id, [])
            if not pl:
                next_change[inst.monitor_id] = now + EMPTY_PLAYLIST_DELAY
                continue

            # Shuffle
            shuffle = False
            try:
                wc = load_wall_config()
                shuffle = wc.get("playback", {}).get(inst.monitor_id, {}).get("shuffle", False)
            except Exception:
                pass

            if shuffle:
                inst.index = random.randint(0, len(pl) - 1)

            asset = pl[inst.index]
            uri = resolve_uri(asset.get("uri", ""))
            name = asset.get("asset", "Unknown")
            duration = max(int(float(asset.get("duration", 10))), 1)

            # Pruefen ob Datei existiert
            if not Path(uri).exists():
                logging.warning("[%s] Datei fehlt: %s", inst.monitor_id, uri)
                inst.index = (inst.index + 1) % len(pl)
                next_change[inst.monitor_id] = now + 1
                continue

            current_index = inst.index
            pending_switches.append((inst, uri, name, duration, current_index))

            if not shuffle:
                inst.index = (inst.index + 1) % len(pl)

        # Alle faelligen Displays GLEICHZEITIG wechseln
        if pending_switches:
            # Barrier: alle Threads warten bis alle bereit, dann gleichzeitig los
            barrier = threading.Barrier(len(pending_switches), timeout=3)

            def sync_load(inst, uri):
                """Warte an Barrier, dann IPC senden — alle gleichzeitig."""
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
                inst.load_file(uri)

            threads = []
            for inst, uri, name, duration, current_index in pending_switches:
                logging.info("[%s] %s (%ds)", inst.monitor_id, name, duration)
                t = threading.Thread(target=sync_load, args=(inst, uri))
                threads.append(t)
                playback_state[inst.monitor_id] = {"index": current_index, "asset": name}

                # Masterclock: naechsten Wechsel auf glatten Zeitpunkt quantisieren
                next_tick = now + duration
                next_tick = int(next_tick) + 1
                next_change[inst.monitor_id] = next_tick

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            write_playback_state(playback_state)

        # Bis zum naechsten faelligen Wechsel schlafen —
        # Grob schlafen bis 10ms vor Ziel, dann Busy-Wait fuer Praezision
        earliest = min(next_change.values()) if next_change else now + 1
        remaining = earliest - time.time()
        if remaining > 0.02:
            # Grob schlafen (spart CPU), 20ms vor Ziel aufhoeren
            time.sleep(remaining - 0.02)
        # Busy-Wait die letzten ~20ms: perf_counter fuer Mikrosekunden-Praezision
        while time.time() < earliest:
            pass  # CPU-Takt als Zeitgeber


if __name__ == "__main__":
    main()
