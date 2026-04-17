#!/usr/bin/env python3
"""Displaywall Slave-Agent — empfaengt Playlists vom Head-Pi, steuert 2x mpv.

Laeuft auf jedem Slave-Pi als systemd-Service.
Kommuniziert mit dem VJ-Manager (Head-Pi) ueber REST-API.

Architektur:
  - HTTP-Server auf Port 8081 (empfaengt Playlists, Steuerbefehle)
  - 2x mpv-Instanz (HDMI-A-1, HDMI-A-2)
  - Asset-Cache: Laedt Assets on-demand vom Head-Pi
  - Status-Report: Temperatur, Playback-State, Speicher
"""

import collections
import hashlib
import json
import logging
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

try:
    import systemd.daemon
    HAS_SYSTEMD = True
except ImportError:
    HAS_SYSTEMD = False

# --- Konfiguration ---

AGENT_PORT = 8081
HEAD_PI = os.environ.get("DISPLAYWALL_HEAD", "head-pi")
HEAD_PORT = 8080

ASSET_DIR = Path.home() / "displaywall_assets"
CONFIG_DIR = Path.home() / ".displaywall"
DISPLAYS_JSON = CONFIG_DIR / "displays.json"
STATE_FILE = CONFIG_DIR / "playback_state.json"
PLAYLIST_FILE = CONFIG_DIR / "playlists.json"

# USB-Mount-Punkt (wird von udev/systemd automatisch gemountet)
USB_MOUNT = Path("/media/displaywall")

CONNECTOR_1 = "HDMI-A-1"
CONNECTOR_2 = "HDMI-A-2"

SYNC_PORT = 1666
SYNC_MAGIC_V3 = "dw3"

# --- Hardware-Counter (CLOCK_MONOTONIC_RAW) ---

_CLOCK = time.CLOCK_MONOTONIC_RAW


def hw_now():
    return time.clock_gettime(_CLOCK)


# --- Sync: TickClock + DeterministicPlaylist + SyncSlave ---

class TickClock:
    """Globaler 1-Sekunden-Takt aus CLOCK_MONOTONIC_RAW."""

    def __init__(self, t0=None):
        self.t0 = t0 if t0 is not None else hw_now()

    def tick(self):
        return int(hw_now() - self.t0)

    def next_tick_hw(self):
        return self.t0 + self.tick() + 1


class DeterministicPlaylist:
    """Deterministische Positionsberechnung aus globalem Tick."""

    def __init__(self, playlist):
        self.playlist = playlist
        self._build_schedule()
        self._last_index = None
        self._offset = 0

    def _build_schedule(self):
        self._boundaries = []
        cumulative = 0
        for item in self.playlist:
            dur = max(int(float(item.get("duration", 10))), 1)
            cumulative += dur
            self._boundaries.append(cumulative)
        self._cycle_len = cumulative if cumulative > 0 else 1

    def update(self, current_tick):
        if not self.playlist:
            return False, None
        pos = (current_tick + self._offset) % self._cycle_len
        if pos < 0:
            pos += self._cycle_len
        new_index = 0
        for i, boundary in enumerate(self._boundaries):
            if pos < boundary:
                new_index = i
                break
        if new_index != self._last_index:
            self._last_index = new_index
            return True, new_index
        return False, None

    def force_next(self):
        if not self.playlist:
            return 0
        idx = self._last_index if self._last_index is not None else 0
        dur = max(int(float(self.playlist[idx].get("duration", 10))), 1)
        self._offset += dur
        new_idx = (idx + 1) % len(self.playlist)
        self._last_index = new_idx
        return new_idx

    def force_prev(self):
        if not self.playlist:
            return 0
        idx = self._last_index if self._last_index is not None else 0
        prev_idx = (idx - 1) % len(self.playlist)
        dur = max(int(float(self.playlist[prev_idx].get("duration", 10))), 1)
        self._offset -= dur
        self._last_index = prev_idx
        return prev_idx

    @property
    def index(self):
        return self._last_index if self._last_index is not None else 0


class SyncSlave:
    """Empfaengt v3-Tick-Pakete vom Head und berechnet PLL-Offset."""

    PLL_WINDOW = 8
    CONVERGE_MIN = 3

    def __init__(self, port=SYNC_PORT, timeout=30):
        self.port = port
        self.timeout = timeout
        self._lock = threading.Lock()
        self._running = False
        self._offsets = collections.deque(maxlen=self.PLL_WINDOW)
        self._last_rx_hw = 0.0
        self._converged = False
        self._master_t0 = None
        self._master_tick = 0

    def start(self):
        self._running = True
        t = threading.Thread(target=self._listen, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(5)
        sock.bind(("", self.port))
        logging.info("SyncSlave: lausche auf Port %d", self.port)

        while self._running:
            try:
                data, addr = sock.recvfrom(512)
                rx_hw = hw_now()
                msg = json.loads(data.decode())
                if msg.get("v") != SYNC_MAGIC_V3:
                    continue

                m_now = msg["m_now"]
                offset = m_now - rx_hw

                with self._lock:
                    new_t0 = msg["t0"]
                    if self._master_t0 is not None and new_t0 != self._master_t0:
                        self._offsets.clear()
                        self._converged = False
                        logging.info("SyncSlave: PLL-Reset (T0 geaendert)")
                    self._master_t0 = new_t0
                    self._master_tick = msg["tick"]
                    self._offsets.append(offset)
                    self._last_rx_hw = rx_hw
                    if not self._converged and len(self._offsets) >= self.CONVERGE_MIN:
                        self._converged = True
                        logging.info("SyncSlave: PLL konvergiert (%d Samples)", self.CONVERGE_MIN)

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logging.warning("SyncSlave: Fehler: %s", e)
        sock.close()

    def _avg_offset(self):
        if not self._offsets:
            return 0.0
        return sum(self._offsets) / len(self._offsets)

    def has_master(self):
        with self._lock:
            return self._converged and (hw_now() - self._last_rx_hw < self.timeout)

    def get_master_t0(self):
        with self._lock:
            return self._master_t0

    def get_local_tick(self):
        """Lokale Tick-Nummer synchron zum Master berechnen."""
        with self._lock:
            if not self._converged or self._master_t0 is None:
                return None
            if hw_now() - self._last_rx_hw > self.timeout:
                return None
            return int(hw_now() + self._avg_offset() - self._master_t0)

    def get_offset_ms(self):
        with self._lock:
            return self._avg_offset() * 1000


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agent] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Globaler State ---

viewers = {}       # {"hdmi1": ViewerThread, "hdmi2": ViewerThread}
playlists = {}     # {"slave1-1": [...], "slave1-2": [...]}
playback_cfg = {}  # {"slave1-1": {"shuffle": false}, ...}
hostname = ""
monitor_ids = []   # z.B. ["slave1-1", "slave1-2"]
_sync_slave = None # Globale Referenz fuer Status-API


def get_hostname():
    """Hostname ermitteln (z.B. 'slave1')."""
    return socket.gethostname()


def get_monitor_ids():
    """Monitor-IDs aus Hostname ableiten: slave1 -> [slave1-1, slave1-2]."""
    h = get_hostname()
    return [f"{h}-1", f"{h}-2"]


# --- Display-Konfiguration ---

_DEFAULT_DISPLAYS = {
    CONNECTOR_1: {"rotation": 0, "resolution": "2560x1440"},
    CONNECTOR_2: {"rotation": 0, "resolution": "2560x1440"},
}


def load_displays():
    try:
        return json.loads(DISPLAYS_JSON.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        save_displays(_DEFAULT_DISPLAYS)
        return _DEFAULT_DISPLAYS.copy()


def save_displays(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DISPLAYS_JSON.write_text(json.dumps(data, indent=2))


# --- Asset-Cache ---

def get_asset_dir():
    """Asset-Verzeichnis: USB wenn vorhanden, sonst SD-Karte."""
    usb_assets = USB_MOUNT / "displaywall_assets"
    if USB_MOUNT.is_mount():
        usb_assets.mkdir(parents=True, exist_ok=True)
        return usb_assets
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    return ASSET_DIR


def cache_asset(uri, asset_name):
    """Asset vom Head-Pi laden falls nicht lokal vorhanden. Gibt lokalen Pfad zurueck."""
    asset_dir = get_asset_dir()

    # Dateiname aus URI extrahieren
    if "/" in uri:
        filename = uri.rsplit("/", 1)[-1]
    else:
        filename = asset_name

    local_path = asset_dir / filename
    if local_path.is_file() and local_path.stat().st_size > 100:
        return str(local_path)

    # Vom Head-Pi herunterladen
    # URI kann /home/head/screenly_assets/UUID.jpg sein
    # oder /data/screenly_assets/UUID.jpg
    import re
    match = re.search(r'screenly_assets/(.+)$', uri)
    if match:
        remote_file = match.group(1)
        url = f"http://{HEAD_PI}:{HEAD_PORT}/assets/{remote_file}"
    else:
        url = uri

    logging.info("Lade Asset: %s -> %s", url, local_path)
    try:
        urllib.request.urlretrieve(url, str(local_path))
        # Kaputte Downloads loeschen (Platzhalter, 404-Seiten etc.)
        if local_path.stat().st_size < 100:
            logging.warning("Download zu klein (%d Bytes), loesche: %s",
                            local_path.stat().st_size, local_path)
            local_path.unlink()
            return None
        return str(local_path)
    except Exception as e:
        logging.error("Download fehlgeschlagen: %s — %s", url, e)
        if local_path.is_file():
            local_path.unlink()
        return None


def get_disk_info():
    """Speicherplatz-Info fuer aktives Asset-Verzeichnis."""
    asset_dir = get_asset_dir()
    try:
        total, used, free = shutil.disk_usage(str(asset_dir))
        return {
            "path": str(asset_dir),
            "total_gb": round(total / (1024**3), 1),
            "used_gb": round(used / (1024**3), 1),
            "free_gb": round(free / (1024**3), 1),
            "usb": USB_MOUNT.is_mount(),
        }
    except Exception:
        return {"path": str(asset_dir), "error": "nicht lesbar"}


# --- Viewer-Thread (mpv-Steuerung) ---

class ViewerThread(threading.Thread):
    """Spielt eine Playlist endlos auf einem HDMI-Ausgang ab."""

    def __init__(self, monitor_id, connector, tick_clock=None, sync_slave=None):
        super().__init__(daemon=True)
        self.monitor_id = monitor_id
        self.connector = connector
        self.playlist = []
        self.shuffle = False
        self.index = 0
        self.current_asset = ""
        self.running = True
        self.process = None
        self._lock = threading.Lock()
        self._tick_clock = tick_clock
        self._sync_slave = sync_slave
        self._counter = None
        self._playlist_changed = False
        self._last_valid_path = None
        self._last_valid_asset = None

    def update_playlist(self, items, shuffle=False):
        with self._lock:
            self.playlist = list(items)
            self.shuffle = shuffle
            self._playlist_changed = True
        logging.info("[%s] Playlist aktualisiert: %d Assets, shuffle=%s",
                     self.monitor_id, len(items), shuffle)

    def stop_playback(self):
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def skip(self, direction=1):
        """Vor- oder zurueckspringen."""
        with self._lock:
            if not self._counter or not self._counter.playlist:
                return
            if direction >= 0:
                self._counter.force_next()
            else:
                self._counter.force_prev()

    def get_state(self):
        return {
            "monitor": self.monitor_id,
            "connector": self.connector,
            "index": self.index,
            "asset": self.current_asset,
            "playlist_length": len(self.playlist),
            "running": self.running,
        }

    def _ipc_send(self, command):
        """IPC-Befehl an mpv senden."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(self._ipc_sock)
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

    def _cleanup_old_mpv(self):
        """Alte/verwaiste mpv-Prozesse fuer diesen Monitor killen."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"mpv.*{self._ipc_sock}"],
                capture_output=True, text=True)
            for pid_str in result.stdout.strip().split("\n"):
                pid_str = pid_str.strip()
                if pid_str:
                    pid = int(pid_str)
                    # Eigenen Prozess nicht killen
                    if self.process and pid == self.process.pid:
                        continue
                    logging.info("[%s] Raeume alten mpv auf (PID %d)", self.monitor_id, pid)
                    os.kill(pid, 9)
        except Exception:
            pass

    def _start_mpv(self, initial_file=None):
        """mpv persistent starten. Mit initial_file direkt ein Bild anzeigen."""
        self._ipc_sock = f"/tmp/mpv-{self.monitor_id}.sock"
        self._cleanup_old_mpv()
        try:
            os.unlink(self._ipc_sock)
        except OSError:
            pass

        rotation = load_displays().get(self.connector, {}).get("rotation", 0)
        wayland = os.environ.get("WAYLAND_DISPLAY")

        cmd = ["mpv", "--no-terminal", f"--input-ipc-server={self._ipc_sock}"]
        if wayland:
            # Unter Wayland: --fs-screen-name nutzt Monitormodell, nicht Connector.
            # Bei identischen Monitoren nicht eindeutig → Screen-Index verwenden.
            # HDMI-A-1 = 0, HDMI-A-2 = 1 (Pi 5 Reihenfolge)
            screen_idx = 0
            if self.connector == "HDMI-A-2":
                screen_idx = 1
            cmd += [
                "--vo=gpu",
                "--gpu-context=wayland",
                "--fullscreen",
                f"--fs-screen={screen_idx}",
            ]
        else:
            cmd += [
                "--vo=gpu",
                "--gpu-context=drm",
                f"--drm-connector={self.connector}",
            ]

        cmd += [
            "--keep-open=yes",
            "--image-display-duration=inf",
            "--background=none",
        ]

        if not initial_file:
            cmd += ["--idle=yes", "--force-window=yes"]

        if rotation:
            cmd.append(f"--video-rotate={rotation}")

        if initial_file:
            cmd.extend(["--", initial_file])

        logging.info("[%s] Starte mpv persistent auf %s", self.monitor_id, self.connector)
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Warten bis Socket bereit
        for _ in range(50):
            if Path(self._ipc_sock).exists():
                time.sleep(0.3)
                return True
            time.sleep(0.1)

        logging.error("[%s] mpv-Socket nicht bereit", self.monitor_id)
        return False

    def _mpv_alive(self):
        return self.process and self.process.poll() is None

    def _get_tick(self):
        """Aktuelle Tick-Nummer — synchron zum Master wenn verfuegbar."""
        if self._sync_slave and self._sync_slave.has_master():
            t = self._sync_slave.get_local_tick()
            if t is not None:
                return t
        if self._tick_clock:
            return self._tick_clock.tick()
        return int(hw_now())

    def _load_image(self, local_path):
        """Bild in mpv laden (startet mpv bei Bedarf). Gibt True bei Erfolg."""
        if not self._mpv_alive():
            if not self._start_mpv(initial_file=local_path):
                return False
            self._first_start = True
            return True

        if self._first_start:
            self._first_start = False
            return True

        if not self._ipc_send(["loadfile", local_path, "replace"]):
            if self._mpv_alive():
                self.process.kill()
            self.process = None
            return False
        return True

    def run(self):
        self._ipc_sock = f"/tmp/mpv-{self.monitor_id}.sock"
        self._first_start = True
        last_tick = -1

        while self.running:
            # Playlist-Aenderung → neuen DeterministicPlaylist erstellen
            with self._lock:
                if self._playlist_changed:
                    self._counter = DeterministicPlaylist(self.playlist)
                    self._playlist_changed = False

            if not self._counter or not self._counter.playlist:
                time.sleep(1)
                continue

            current_tick = self._get_tick()
            new_tick = current_tick != last_tick

            if not new_tick:
                # Warten bis naechster Tick
                self._wait_next_tick()
                continue

            last_tick = current_tick

            # Shuffle: bei Wechsel zufaelligen Index setzen
            with self._lock:
                shuffle = self.shuffle

            if shuffle:
                should_switch, _ = self._counter.update(current_tick)
                if should_switch:
                    new_index = random.randint(0, len(self._counter.playlist) - 1)
                    self._counter._last_index = new_index
                else:
                    self._wait_next_tick()
                    continue
            else:
                should_switch, new_index = self._counter.update(current_tick)

            if not should_switch:
                self._wait_next_tick()
                continue

            # Asset laden und anzeigen
            item = self._counter.playlist[new_index]
            asset_name = item.get("asset", "")
            uri = item.get("uri", "")
            local_path = cache_asset(uri, asset_name)

            if not local_path:
                logging.warning("[%s] Asset defekt/fehlt: %s — ersetze mit vorigem",
                                self.monitor_id, asset_name)
                if self._last_valid_path:
                    local_path = self._last_valid_path
                    asset_name = self._last_valid_asset
                else:
                    self._counter.force_next()
                    self._wait_next_tick()
                    continue

            self._last_valid_path = local_path
            self._last_valid_asset = asset_name
            self.current_asset = asset_name
            self.index = new_index

            write_playback_state(self.monitor_id, new_index, asset_name)
            logging.info("[%s] Bild: %s (idx %d, tick %d)",
                         self.monitor_id, asset_name, new_index, current_tick)

            if not self._load_image(local_path):
                time.sleep(1)
                continue

            self._wait_next_tick()

    def _wait_next_tick(self):
        """Bis zum naechsten Tick schlafen (200ms-Intervalle, Busy-Wait letzte 20ms)."""
        if not self._tick_clock:
            time.sleep(0.5)
            return
        next_hw = self._tick_clock.next_tick_hw()
        # Sync-korrigierte Clock: wenn SyncSlave aktiv, T0-Offset beruecksichtigen
        if self._sync_slave and self._sync_slave.has_master():
            master_t0 = self._sync_slave.get_master_t0()
            if master_t0 is not None:
                # Tick-Grenze basierend auf Master-T0 + Offset berechnen
                with self._sync_slave._lock:
                    avg_off = self._sync_slave._avg_offset()
                local_tick = int(hw_now() + avg_off - master_t0)
                next_hw = master_t0 - avg_off + local_tick + 1
        delta = next_hw - hw_now()
        if delta <= 0:
            return
        # Grob schlafen, letzte 20ms busy-wait
        while hw_now() < next_hw - 0.02:
            remaining = next_hw - hw_now() - 0.02
            if remaining <= 0:
                break
            if not self.running:
                return
            time.sleep(min(0.2, remaining))
        # Busy-Wait fuer Praezision
        while hw_now() < next_hw:
            pass


def write_playback_state(monitor_id, index, asset_name):
    try:
        state = {}
        if STATE_FILE.is_file():
            state = json.loads(STATE_FILE.read_text())
        state[monitor_id] = {"index": index, "asset": asset_name}
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


# --- HTTP-API ---

class AgentHandler(SimpleHTTPRequestHandler):
    """REST-API fuer den Slave-Agent."""

    def log_message(self, fmt, *args):
        logging.debug("HTTP %s", fmt % args)

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            self.handle_status()
        elif self.path == "/api/playback":
            self.handle_playback()
        elif self.path == "/api/disk":
            self.send_json(get_disk_info())
        elif self.path.startswith("/assets/"):
            self.handle_asset()
        else:
            self.send_json({"agent": hostname, "monitors": monitor_ids})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if self.path == "/api/playlist":
            self.handle_set_playlist(body)
        elif self.path == "/api/command":
            self.handle_command(body)
        elif self.path == "/api/displays":
            self.handle_set_displays(body)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def handle_status(self):
        """System-Status: Temperatur, Speicher, Viewer-State."""
        temp = _run(["vcgencmd", "measure_temp"])
        throttle = _run(["vcgencmd", "get_throttled"])

        # Sync-Status (global, nicht pro Handler-Instanz)
        sync_info = {}
        if _sync_slave:
            sync_info = {
                "has_master": _sync_slave.has_master(),
                "offset_ms": round(_sync_slave.get_offset_ms(), 1),
                "master_t0": _sync_slave.get_master_t0(),
            }
            lt = _sync_slave.get_local_tick()
            if lt is not None:
                sync_info["local_tick"] = lt

        status = {
            "hostname": hostname,
            "ip": _get_ip(),
            "temperature": temp,
            "throttle": throttle.split("=")[-1] if "=" in throttle else throttle,
            "uptime": _get_uptime(),
            "disk": get_disk_info(),
            "memory": _get_memory(),
            "viewers": {vid: viewers[vid].get_state() for vid in viewers},
            "sync": sync_info,
        }
        self.send_json(status)

    def handle_playback(self):
        """Aktueller Playback-State aller Viewer."""
        states = {vid: viewers[vid].get_state() for vid in viewers}
        self.send_json(states)

    def handle_set_playlist(self, body):
        """Playlist setzen: {"monitor_id": "slave1-1", "items": [...], "shuffle": false}"""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, 400)
            return

        mid = data.get("monitor_id", "")
        items = data.get("items", [])
        shuffle = data.get("shuffle", False)

        if mid not in viewers:
            self.send_json({"error": f"unknown monitor: {mid}"}, 404)
            return

        viewers[mid].update_playlist(items, shuffle)

        # Playlist persistent speichern
        playlists[mid] = items
        playback_cfg[mid] = {"shuffle": shuffle}
        save_playlists()

        self.send_json({"ok": True, "monitor": mid, "count": len(items)})

    def handle_command(self, body):
        """Steuerbefehl: {"command": "next|prev|stop|play", "monitor": "slave1-1"|"all"}"""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, 400)
            return

        cmd = data.get("command", "")
        target = data.get("monitor", "all")

        targets = list(viewers.keys()) if target == "all" else [target]

        for mid in targets:
            if mid not in viewers:
                continue
            if cmd == "next":
                viewers[mid].skip(1)
            elif cmd == "prev":
                viewers[mid].skip(-1)
            elif cmd == "stop":
                viewers[mid].stop_playback()
            elif cmd == "play":
                if not viewers[mid].running:
                    start_viewer(mid)

        self.send_json({"ok": True, "command": cmd, "targets": targets})

    def handle_set_displays(self, body):
        """Display-Konfiguration setzen (Rotation)."""
        try:
            data = json.loads(body)
            save_displays(data)
            self.send_json({"ok": True, "hint": "Reboot noetig fuer Rotation"})
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, 400)

    def handle_asset(self):
        """Lokales Asset ausliefern (fuer Preview im VJ-Manager)."""
        filename = self.path.split("/assets/", 1)[-1]
        if ".." in filename or "/" in filename:
            self.send_json({"error": "forbidden"}, 403)
            return
        asset_dir = get_asset_dir()
        fpath = asset_dir / filename
        if not fpath.is_file():
            self.send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        ct = "application/octet-stream"
        lower = filename.lower()
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            ct = "image/jpeg"
        elif lower.endswith(".png"):
            ct = "image/png"
        elif lower.endswith(".mp4"):
            ct = "video/mp4"
        elif lower.endswith(".webm"):
            ct = "video/webm"
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", fpath.stat().st_size)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(fpath, "rb") as f:
            shutil.copyfileobj(f, self.wfile)


# --- Hilfsfunktionen ---

def _run(cmd, timeout=3):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def _get_uptime():
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
        days = secs // 86400
        hours = (secs % 86400) // 3600
        mins = (secs % 3600) // 60
        if days:
            return f"{days}d {hours}h {mins}m"
        if hours:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return ""


def _get_memory():
    try:
        with open("/proc/meminfo") as f:
            raw = f.read()
        info = {}
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        if total:
            used = total - avail
            return f"{used // 1024}/{total // 1024} MB ({int(used / total * 100)}%)"
    except Exception:
        pass
    return ""


def save_playlists():
    """Playlists persistent speichern."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"playlists": playlists, "playback": playback_cfg}
    PLAYLIST_FILE.write_text(json.dumps(data, indent=2))


def load_playlists():
    """Gespeicherte Playlists laden (fuer Neustart ohne Head-Pi)."""
    global playlists, playback_cfg
    try:
        data = json.loads(PLAYLIST_FILE.read_text())
        playlists = data.get("playlists", {})
        playback_cfg = data.get("playback", {})
    except (FileNotFoundError, json.JSONDecodeError):
        playlists = {}
        playback_cfg = {}


def pull_wall_from_head():
    """Holt die aktuelle wall_config.json vom Head-Pi und uebernimmt
    die fuer diesen Slave relevanten Playlists.

    Das loest den Fall, dass der Slave frisch bootet bevor der Head
    via POST /api/playlist pushen kann (oder der Head zwischenzeitlich
    neu gestartet wurde).

    Gibt True zurueck wenn der Head erreichbar war, False sonst.
    """
    url = f"http://{HEAD_PI}:{HEAD_PORT}/api/wall"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            wall = json.loads(resp.read())
    except Exception as e:
        logging.info("Pull vom Head nicht moeglich (%s) — nutze lokalen Cache", e)
        return False

    pls = wall.get("playlists", {})
    pb = wall.get("playback", {})
    changed = False
    for mid in monitor_ids:
        if mid not in pls:
            continue
        new_items = pls[mid]
        new_shuffle = pb.get(mid, {}).get("shuffle", False)
        old_items = playlists.get(mid, [])
        old_shuffle = playback_cfg.get(mid, {}).get("shuffle", False)
        if new_items == old_items and new_shuffle == old_shuffle:
            continue
        playlists[mid] = new_items
        playback_cfg[mid] = {"shuffle": new_shuffle}
        vt = viewers.get(mid)
        if vt:
            vt.update_playlist(new_items, new_shuffle)
        changed = True
        logging.info("[%s] Pull vom Head: %d Assets (shuffle=%s)",
                     mid, len(new_items), new_shuffle)
    if changed:
        save_playlists()
    return True


def pull_loop():
    """Zyklischer Pull vom Head alle 30s.

    Laeuft im Hintergrund. Kein Stoppen bei Fehlern — Slave haengt an
    seiner lokalen Kopie wenn Head weg ist.
    """
    while True:
        time.sleep(30)
        try:
            pull_wall_from_head()
        except Exception as e:
            logging.warning("Pull-Loop Ausnahme: %s", e)


def start_viewer(monitor_id, tick_clock=None, sync_slave=None):
    """Viewer-Thread fuer einen Monitor starten."""
    connector = CONNECTOR_1 if monitor_id.endswith("-1") else CONNECTOR_2
    vt = ViewerThread(monitor_id, connector, tick_clock=tick_clock, sync_slave=sync_slave)
    viewers[monitor_id] = vt

    # Gespeicherte Playlist laden falls vorhanden
    if monitor_id in playlists:
        shuffle = playback_cfg.get(monitor_id, {}).get("shuffle", False)
        vt.update_playlist(playlists[monitor_id], shuffle)

    vt.start()
    logging.info("Viewer gestartet: %s auf %s", monitor_id, connector)


# --- Main ---

def main():
    global hostname, monitor_ids, _sync_slave

    hostname = get_hostname()
    monitor_ids = get_monitor_ids()

    logging.info("Displaywall Agent gestartet: %s", hostname)
    logging.info("Monitore: %s", monitor_ids)
    logging.info("Asset-Verzeichnis: %s (USB: %s)", get_asset_dir(), USB_MOUNT.is_mount())

    # Verzeichnisse anlegen
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    # Gespeicherte Playlists laden (Fallback, falls Head nicht erreichbar)
    load_playlists()

    # Einmaliger Pull vom Head (ueberschreibt lokale Kopie falls Head online)
    pull_wall_from_head()

    # SCHED_FIFO fuer praeziseres Timing (Realtime-Scheduling)
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))
        logging.info("SCHED_FIFO aktiv (Prioritaet 1)")
    except PermissionError:
        logging.warning("SCHED_FIFO nicht verfuegbar — normales Scheduling")

    # Sync-Slave starten — empfaengt Tick-Pakete vom Head
    sync_slave = SyncSlave()
    _sync_slave = sync_slave
    sync_slave.start()
    logging.info("SyncSlave aktiv (Port %d)", SYNC_PORT)

    # TickClock — wird genutzt wenn kein Master verfuegbar
    tick_clock = TickClock()
    logging.info("TickClock gestartet (T0=%.3f)", tick_clock.t0)

    # Viewer-Threads starten (mit Sync)
    for mid in monitor_ids:
        start_viewer(mid, tick_clock=tick_clock, sync_slave=sync_slave)

    # Zyklischer Pull (30s) — faengt Head-Neustarts + GUI-Aenderungen auf
    threading.Thread(target=pull_loop, daemon=True).start()
    logging.info("Pull-Loop aktiv (alle 30s)")

    # Watchdog-Thread (systemd)
    if HAS_SYSTEMD:
        def watchdog_loop():
            while True:
                # Meldung an systemd: Dienst ist bereit/lebt noch
                systemd.daemon.notify("WATCHDOG=1")
                time.sleep(30)
        threading.Thread(target=watchdog_loop, daemon=True).start()
        logging.info("Systemd-Watchdog aktiviert (30s Polling)")

    # HTTP-Server starten
    server = HTTPServer(("0.0.0.0", AGENT_PORT), AgentHandler)
    logging.info("API lauscht auf Port %d", AGENT_PORT)

    def shutdown(sig, frame):
        logging.info("Beende...")
        for vid in viewers:
            viewers[vid].stop_playback()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


if __name__ == "__main__":
    main()
