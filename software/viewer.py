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
from displaywall.sync import SyncMaster, TickClock, DeterministicPlaylist, hw_now
from displaywall.wall import load_wall_config, WALL_CONFIG

PLAYBACK_STATE_FILE = Path(__file__).parent / "displaywall" / "playback_state.json"
COMMAND_FILE = Path(__file__).parent / "displaywall" / "viewer_cmd.json"
MPV_STARTUP_TIMEOUT = 10
EMPTY_PLAYLIST_DELAY = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [viewer] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
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
        self._playlist_loaded = False
        self._playlist_size = 0
        self._pl_index_map = {}  # wall-config index -> mpv playlist index
        self._preloaded_uri = None

    def start(self):
        """mpv im Idle-Modus starten."""
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass

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
            sock.settimeout(0.5)
            sock.connect(self.sock_path)
            payload = json.dumps({"command": command}) + "\n"
            sock.sendall(payload.encode())
            sock.settimeout(0.1)
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

    def load_playlist(self, uris_with_indices):
        """Alle Items in mpv-Playlist vorladen fuer sofortigen Wechsel.

        uris_with_indices: Liste von (wall_config_index, uri) Tupeln.
        """
        self._ipc_send(["playlist-clear"])
        self._pl_index_map = {}
        mpv_idx = 0
        for wall_idx, uri in uris_with_indices:
            mode = "append-play" if mpv_idx == 0 else "append"
            self._ipc_send(["loadfile", uri, mode])
            self._pl_index_map[wall_idx] = mpv_idx
            mpv_idx += 1
        self._playlist_loaded = True
        self._playlist_size = mpv_idx
        logging.info("[%s] Playlist vorgeladen: %d Items", self.monitor_id, mpv_idx)

    def preload_next(self, uri):
        """Naechstes Bild vorladen (append). mpv decodiert im Hintergrund."""
        ok = self._ipc_send(["loadfile", uri, "append"])
        if ok:
            self._preloaded_uri = uri
            logging.info("[%s] Pre-decode: %s", self.monitor_id, Path(uri).name)
        return ok

    def switch_preloaded(self, uri):
        """Zum vorgeladenen Bild wechseln (playlist-next). Sofort, kein Decode."""
        if getattr(self, '_preloaded_uri', None) != uri:
            return False
        ok = self._ipc_send(["playlist-next", "force"])
        if ok:
            self._ipc_send(["playlist-remove", "0"])
            self.current_uri = uri
            self._preloaded_uri = None
        return ok

    def jump_to(self, index, uri=None):
        """Bild wechseln — preloaded (instant) oder loadfile replace (Fallback)."""
        if not uri:
            return False
        # Vorgeladen? → playlist-next (sofort)
        if self.switch_preloaded(uri):
            return True
        # Fallback: loadfile replace
        if self._preloaded_uri:
            logging.debug("[%s] Preload-Miss: erwartet %s, geladen %s",
                          self.monitor_id, Path(uri).name,
                          Path(self._preloaded_uri).name if self._preloaded_uri else "nix")
        self._preloaded_uri = None
        return self.load_file(uri)

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
    # Realtime-Scheduling fuer praezises Timing
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))
        logging.info("SCHED_FIFO aktiv (Prioritaet 1)")
    except PermissionError:
        logging.warning("SCHED_FIFO nicht verfuegbar (keine Berechtigung)")

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

    # Sync-Master starten — Slave-IPs aus slaves.json fuer Unicast
    slave_ips = []
    slaves_json = Path(__file__).parent / "displaywall" / "slaves.json"
    try:
        slaves = json.loads(slaves_json.read_text())
        slave_ips = [s["ip"] for s in slaves.values() if s.get("ip")]
    except Exception:
        pass
    sync_master = SyncMaster(slave_ips=slave_ips)
    logging.info("Sync-Master aktiv (Port 1666, Slaves: %s)", slave_ips or "nur Broadcast")

    # Playback-Loop — Tick-Counter-basiert
    tick_clock = TickClock()
    logging.info("TickClock gestartet (T0=%.3f)", tick_clock.t0)

    last_wall_mtime = 0
    last_disp_mtime = 0
    playlists = {}
    counters = {}       # monitor_id -> DeterministicPlaylist
    shuffle_flags = {}  # monitor_id -> bool
    playback_state = {}
    paused = set()      # Monitor-IDs die pausiert/gestoppt sind
    force_next = set()  # Monitor-IDs die einmalig weiterschalten (next/prev im Stop)
    last_tick = -1      # Letzter verarbeiteter Tick

    while True:
        current_tick = tick_clock.tick()

        # Abgestuerzte mpv-Instanzen neu starten
        for inst in instances:
            if not inst.is_alive():
                logging.warning("[%s] mpv abgestuerzt — Neustart", inst.monitor_id)
                disp_config = load_displays()
                rotation = disp_config.get(inst.connector, {}).get("rotation", 0)
                inst.rotation = rotation
                inst.start()
                inst.current_uri = None
                inst._playlist_loaded = False
                # DeterministicPlaylist braucht keinen Reset —
                # Position wird aus Tick berechnet

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
                shuffle_flags[inst.monitor_id] = wc.get("playback", {}).get(inst.monitor_id, {}).get("shuffle", False)
                if new_pl != old_pl:
                    logging.info("[%s] Playlist: %d Assets", inst.monitor_id, len(new_pl))
                    counters[inst.monitor_id] = DeterministicPlaylist(new_pl)

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
                        counter = counters.get(inst.monitor_id)
                        if not counter or not counter.playlist:
                            continue
                        if action == "next":
                            counter.force_next()
                            force_next.add(inst.monitor_id)
                        elif action == "prev":
                            counter.force_prev()
                            force_next.add(inst.monitor_id)
                        elif action in ("stop", "pause"):
                            paused.add(inst.monitor_id)
                        elif action == "play":
                            paused.discard(inst.monitor_id)
                        logging.info("[%s] Befehl: %s", inst.monitor_id, action)
            except Exception as e:
                logging.warning("Command-Datei Fehler: %s", e)

        # Tick-basierte Wechsellogik
        # Nur bei neuem Tick oder force_next auswerten
        new_tick = current_tick != last_tick
        if new_tick:
            last_tick = current_tick

        # Pre-Decode: naechstes Bild 3s vor Wechsel vorladen
        PRELOAD_SECONDS = 3
        if new_tick:
            for inst in instances:
                counter = counters.get(inst.monitor_id)
                if not counter or not counter.playlist or len(counter.playlist) <= 1:
                    continue
                if inst.monitor_id in paused:
                    continue
                if getattr(inst, '_preloaded_uri', None):
                    continue
                next_switch = counter.next_switch_tick(current_tick)
                ticks_until = next_switch - current_tick
                if 0 < ticks_until <= PRELOAD_SECONDS:
                    next_idx = counter.peek_next_index(current_tick)
                    next_asset = counter.playlist[next_idx]
                    next_uri = resolve_uri(next_asset.get("uri", ""))
                    if Path(next_uri).exists():
                        inst.preload_next(next_uri)

        pending_switches = []
        for inst in instances:
            counter = counters.get(inst.monitor_id)
            if not counter or not counter.playlist:
                continue

            # Force next/prev (auch ohne neuen Tick)
            if inst.monitor_id in force_next:
                force_next.discard(inst.monitor_id)
                new_index = counter.index  # Wurde in Command-Verarbeitung gesetzt
                pl = counter.playlist
                asset = pl[new_index]
                uri = resolve_uri(asset.get("uri", ""))
                name = asset.get("asset", "Unknown")
                if Path(uri).exists():
                    pending_switches.append((inst, uri, name, new_index))
                    playback_state[inst.monitor_id] = {"index": new_index, "asset": name}
                continue

            # Pausiert: Counter nicht weiterzaehlen
            if inst.monitor_id in paused:
                continue

            # Nur bei neuem Tick den Counter updaten
            if not new_tick:
                continue

            # Shuffle pruefen (aus gecachtem Config)
            shuffle = shuffle_flags.get(inst.monitor_id, False)

            if shuffle:
                # Bei Wechsel zufaelligen Index waehlen
                old_remaining = counter.remaining
                should_switch, _ = counter.update(current_tick)
                if should_switch:
                    new_index = counter.set_random_index()
                else:
                    continue
            else:
                should_switch, new_index = counter.update(current_tick)

            if not should_switch:
                continue

            pl = counter.playlist
            asset = pl[new_index]
            uri = resolve_uri(asset.get("uri", ""))
            name = asset.get("asset", "Unknown")

            if not Path(uri).exists():
                logging.warning("[%s] Datei fehlt: %s", inst.monitor_id, uri)
                counter.force_next()
                continue

            pending_switches.append((inst, uri, name, new_index))
            playback_state[inst.monitor_id] = {"index": new_index, "asset": name}

        # Alle faelligen Displays GLEICHZEITIG wechseln
        if pending_switches:
            barrier = threading.Barrier(len(pending_switches), timeout=3)

            def sync_load(inst, uri, pl_index):
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
                inst.jump_to(pl_index, uri)

            threads = []
            for inst, uri, name, current_index in pending_switches:
                logging.info("[%s] %s (idx %d, tick %d)", inst.monitor_id, name, current_index, current_tick)
                t = threading.Thread(target=sync_load, args=(inst, uri, current_index))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            write_playback_state(playback_state)

        # Sync-Heartbeat an Slaves — JEDEN Tick senden (nicht nur bei Bildwechsel)
        if new_tick:
            sync_master.send_tick(0, tick_clock=tick_clock)

        # Sleep bis naechster Tick (200ms-Intervalle, Busy-Wait letzte 20ms)
        next_tick_hw = tick_clock.next_tick_hw()
        # In wall-clock umrechnen fuer sleep
        delta_to_tick = next_tick_hw - hw_now()
        sleep_until = time.time() + min(delta_to_tick, 1.0)
        while time.time() < sleep_until - 0.02:
            if COMMAND_FILE.exists():
                break
            time.sleep(min(0.2, max(0, sleep_until - time.time() - 0.02)))
        # Busy-Wait die letzten ~20ms
        if not COMMAND_FILE.exists():
            while hw_now() < next_tick_hw:
                pass


if __name__ == "__main__":
    main()
