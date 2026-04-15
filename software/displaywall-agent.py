#!/usr/bin/env python3
"""Displaywall Slave-Agent — empfaengt Playlists vom Head-Pi, steuert 2x mpv.

Laeuft auf jedem Slave-Pi als systemd-Service.
Architektur identisch zum Head-Viewer:
  - 2x persistente mpv-Instanzen (IPC via Unix-Socket)
  - Playlist aus lokaler Kopie von wall_config.json
  - Sync-Empfaenger: UDP-Takt vom Head-Pi fuer gleichzeitigen Bildwechsel
  - HTTP-Server auf Port 8081 (Status, Playlist-Empfang, Steuerbefehle)
  - Asset-Cache: laedt Bilder on-demand vom Head-Pi
"""

import json
import logging
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# --- Konfiguration ---

AGENT_PORT = 8081
HEAD_PI = os.environ.get("DISPLAYWALL_HEAD", "head-pi")
HEAD_PORT = 8080

ASSET_DIR = Path.home() / "displaywall_assets"
CONFIG_DIR = Path.home() / ".displaywall"
DISPLAYS_JSON = CONFIG_DIR / "displays.json"
PLAYBACK_STATE_FILE = CONFIG_DIR / "playback_state.json"
PLAYLIST_FILE = CONFIG_DIR / "playlists.json"
COMMAND_FILE = CONFIG_DIR / "viewer_cmd.json"
USB_MOUNT = Path("/media/displaywall")

CONNECTOR_1 = "HDMI-A-1"
CONNECTOR_2 = "HDMI-A-2"

MPV_STARTUP_TIMEOUT = 10
EMPTY_PLAYLIST_DELAY = 5
SYNC_PORT = 1666

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agent] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


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
    """Asset vom Head-Pi laden falls nicht lokal vorhanden."""
    asset_dir = get_asset_dir()
    if "/" in uri:
        filename = uri.rsplit("/", 1)[-1]
    else:
        filename = asset_name

    local_path = asset_dir / filename
    if local_path.is_file() and local_path.stat().st_size > 100:
        return str(local_path)

    match = re.search(r'screenly_assets/(.+)$', uri)
    if match:
        remote_file = match.group(1)
        url = f"http://{HEAD_PI}:{HEAD_PORT}/assets/{remote_file}"
    else:
        url = uri

    logging.info("Lade Asset: %s -> %s", url, local_path)
    try:
        urllib.request.urlretrieve(url, str(local_path))
        if local_path.stat().st_size < 100:
            logging.warning("Download zu klein (%d Bytes): %s",
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


# --- MpvInstance (identisch zum Head-Viewer) ---

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
                "--vo=gpu", "--gpu-context=wayland", "--fullscreen",
                f"--fs-screen-name={self.connector}",
            ]
        else:
            cmd += [
                "--vo=gpu", "--gpu-context=drm",
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

        for _ in range(MPV_STARTUP_TIMEOUT * 10):
            if Path(self.sock_path).exists():
                time.sleep(0.3)
                return True
            time.sleep(0.1)

        logging.error("[%s] mpv-Socket nicht bereit", self.monitor_id)
        return False

    def _ipc_send(self, command):
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
        ok = self._ipc_send(["loadfile", uri, "replace"])
        if ok:
            self.current_uri = uri
        return ok

    def load_playlist(self, uris_with_indices):
        """Alle Items in mpv-Playlist vorladen fuer sofortigen Wechsel."""
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

    def jump_to(self, index, uri=None):
        """Bild wechseln per loadfile replace."""
        if uri:
            return self.load_file(uri)
        return False

    def set_rotation(self, rotation):
        if rotation != self.rotation:
            logging.info("[%s] Rotation: %d -> %d",
                         self.monitor_id, self.rotation, rotation)
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


# --- Sync-Empfaenger (Hardware-Counter PLL) ---

import collections

_CLOCK = time.CLOCK_MONOTONIC_RAW


def _hw_now():
    return time.clock_gettime(_CLOCK)


class SyncReceiver:
    """Empfaengt UDP-Takt vom Head-Pi mit Hardware-Counter-basierter PLL.

    Unterstuetzt v2 (Legacy: m_now + m_next) und v3 (Tick-Counter: t0 + tick).
    Slave misst lokale CLOCK_MONOTONIC_RAW bei Empfang, berechnet Offset
    per gleitendem Durchschnitt und leitet lokalen Wechselzeitpunkt ab.
    """

    PLL_WINDOW = 8
    CONVERGE_MIN = 3

    def __init__(self, port=SYNC_PORT, timeout=30):
        self.port = port
        self.timeout = timeout
        self._lock = threading.Lock()
        self._running = False
        # PLL-State
        self._offsets = collections.deque(maxlen=self.PLL_WINDOW)
        self._last_rx_hw = 0.0
        self._last_delta = 0.0
        self._converged = False
        # v3-State
        self._master_t0 = None
        self._master_tick = 0
        self._v3_active = False

    def start(self):
        self._running = True
        threading.Thread(target=self._listen, daemon=True).start()

    def stop(self):
        self._running = False

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(5)
        sock.bind(("", self.port))
        logging.info("SyncReceiver: lausche auf Port %d (HW-Counter PLL)", self.port)

        while self._running:
            try:
                data, addr = sock.recvfrom(512)
                rx_hw = _hw_now()
                msg = json.loads(data.decode())
                version = msg.get("v")
                if version not in ("dw2", "dw3"):
                    continue

                m_now = msg["m_now"]
                offset = m_now - rx_hw

                with self._lock:
                    self._offsets.append(offset)
                    self._last_rx_hw = rx_hw
                    self._converged = len(self._offsets) >= self.CONVERGE_MIN

                    if version == "dw3":
                        new_t0 = msg["t0"]
                        # PLL-Reset bei T0-Wechsel (Master-Neustart)
                        if self._master_t0 is not None and new_t0 != self._master_t0:
                            self._offsets.clear()
                            self._converged = False
                            logging.info("SyncReceiver: PLL-Reset (T0 geaendert: %.3f -> %.3f)",
                                         self._master_t0, new_t0)
                            self._offsets.append(offset)  # Erstes Sample neu
                        self._master_t0 = new_t0
                        self._master_tick = msg["tick"]
                        self._v3_active = True
                        self._last_delta = 0
                    else:
                        m_next = msg["m_next"]
                        self._last_delta = m_next - m_now

                    if len(self._offsets) == self.CONVERGE_MIN:
                        logging.info("SyncReceiver: PLL konvergiert (%d Samples, %s)",
                                     self.CONVERGE_MIN, version)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logging.warning("SyncReceiver: Empfangs-Fehler: %s", e)
        sock.close()

    def _avg_offset(self):
        if not self._offsets:
            return 0.0
        return sum(self._offsets) / len(self._offsets)

    def get_next_switch(self):
        """Naechster Wechselzeitpunkt in lokaler CLOCK_MONOTONIC_RAW (Sekunden).
        Gibt 0.0 zurueck wenn PLL nicht konvergiert oder Signal veraltet.
        Nur fuer v2-Modus."""
        with self._lock:
            if not self._converged:
                return 0.0
            if _hw_now() - self._last_rx_hw > self.timeout:
                return 0.0
            return self._last_rx_hw + self._last_delta

    def has_master(self):
        with self._lock:
            if not self._converged:
                return False
            return _hw_now() - self._last_rx_hw < self.timeout

    def is_v3(self):
        """True wenn Master im v3 Tick-Counter Modus."""
        with self._lock:
            return self._v3_active and self._converged

    def get_local_tick(self):
        """Lokale Tick-Nummer berechnen (v3 Modus).
        Gibt (tick, t0) zurueck, oder (None, None) wenn v3 nicht aktiv."""
        with self._lock:
            if not self._v3_active or not self._converged:
                return None, None
            if _hw_now() - self._last_rx_hw > self.timeout:
                return None, None
            avg_off = self._avg_offset()
            local_tick = int(_hw_now() + avg_off - self._master_t0)
            return local_tick, self._master_t0

    def get_master_t0(self):
        with self._lock:
            return self._master_t0


class TickClock:
    """Globaler 1-Sekunden-Takt aus CLOCK_MONOTONIC_RAW."""

    def __init__(self, t0=None):
        self.t0 = t0 if t0 is not None else _hw_now()

    def tick(self):
        return int(_hw_now() - self.t0)

    def next_tick_hw(self):
        return self.t0 + self.tick() + 1


class DisplayCounter:
    """Per-Display Countdown-Zaehler fuer Bildwechsel."""

    def __init__(self, playlist, start_index=0):
        self.playlist = playlist
        self.index = start_index
        self._counter = self._get_duration(start_index)
        self._last_tick = None

    def _get_duration(self, index):
        if not self.playlist:
            return 5
        item = self.playlist[index % max(len(self.playlist), 1)]
        return max(int(float(item.get("duration", 10))), 1)

    def update(self, current_tick):
        if self._last_tick is None:
            self._last_tick = current_tick
            return True, self.index
        elapsed = current_tick - self._last_tick
        self._last_tick = current_tick
        if elapsed <= 0:
            return False, None
        self._counter -= elapsed
        if self._counter <= 0:
            self.index = (self.index + 1) % max(len(self.playlist), 1)
            self._counter = self._get_duration(self.index)
            return True, self.index
        return False, None

    def force_next(self):
        self.index = (self.index + 1) % max(len(self.playlist), 1)
        self._counter = self._get_duration(self.index)
        return self.index

    def force_prev(self):
        self.index = (self.index - 1) % max(len(self.playlist), 1)
        self._counter = self._get_duration(self.index)
        return self.index

    def set_playlist(self, playlist):
        self.playlist = playlist
        self.index = 0
        self._counter = self._get_duration(0)
        self._last_tick = None

    def set_random_index(self):
        if self.playlist:
            self.index = random.randint(0, len(self.playlist) - 1)
        return self.index

    @property
    def remaining(self):
        return self._counter


# --- Playlist-Persistenz ---

def save_playlists(playlists, playback_cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"playlists": playlists, "playback": playback_cfg}
    PLAYLIST_FILE.write_text(json.dumps(data, indent=2))


def load_playlists():
    try:
        data = json.loads(PLAYLIST_FILE.read_text())
        return data.get("playlists", {}), data.get("playback", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}


def write_playback_state(states):
    try:
        PLAYBACK_STATE_FILE.write_text(json.dumps(states))
    except Exception:
        pass


# --- HTTP-API ---

# Globale Referenzen (werden in main() gesetzt)
_instances = []
_playlists = {}
_playback_cfg = {}
_playback_state = {}
_hostname = ""
_monitor_ids = []


class AgentHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        if self.path == "/api/status":
            self._handle_status()
        elif self.path == "/api/playback":
            self._send_json(_playback_state)
        elif self.path == "/api/disk":
            self._send_json(get_disk_info())
        elif self.path.startswith("/assets/"):
            self._handle_asset()
        else:
            self._send_json({"agent": _hostname, "monitors": _monitor_ids})

    def do_POST(self):
        data = self._read_body()

        if self.path == "/api/playlist":
            self._handle_set_playlist(data)
        elif self.path == "/api/command":
            self._handle_command(data)
        elif self.path == "/api/displays":
            save_displays(data)
            self._send_json({"ok": True})
        elif self.path == "/api/rotation":
            connector = data.get("connector", "")
            rotation = data.get("rotation", 0)
            displays = load_displays()
            if connector in displays:
                displays[connector]["rotation"] = rotation
            else:
                displays[connector] = {"rotation": rotation, "resolution": "2560x1440"}
            save_displays(displays)
            self._send_json({"ok": True})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_status(self):
        temp = _run(["vcgencmd", "measure_temp"])
        throttle = _run(["vcgencmd", "get_throttled"])
        viewers_state = {}
        for inst in _instances:
            viewers_state[inst.monitor_id] = {
                "monitor": inst.monitor_id,
                "connector": inst.connector,
                "index": inst.index,
                "asset": (_playback_state.get(inst.monitor_id, {})
                          .get("asset", "")),
                "playlist_length": len(_playlists.get(inst.monitor_id, [])),
                "running": inst.is_alive(),
            }
        self._send_json({
            "hostname": _hostname,
            "ip": _get_ip(),
            "temperature": temp,
            "throttle": (throttle.split("=")[-1]
                         if "=" in throttle else throttle),
            "uptime": _get_uptime(),
            "disk": get_disk_info(),
            "memory": _get_memory(),
            "viewers": viewers_state,
        })

    def _handle_set_playlist(self, data):
        mid = data.get("monitor_id", "")
        items = data.get("items", [])
        shuffle = data.get("shuffle", False)
        _playlists[mid] = items
        _playback_cfg[mid] = {"shuffle": shuffle}
        save_playlists(_playlists, _playback_cfg)
        logging.info("[%s] Playlist aktualisiert: %d Assets", mid, len(items))
        self._send_json({"ok": True, "monitor": mid, "count": len(items)})

    def _handle_command(self, data):
        cmd_action = data.get("command", data.get("cmd", ""))
        target = data.get("monitor", "all")
        # Schreibe Command-Datei fuer den Viewer-Loop
        COMMAND_FILE.write_text(json.dumps({
            "cmd": cmd_action, "monitor": target
        }))
        self._send_json({"ok": True, "command": cmd_action})

    def _handle_asset(self):
        filename = self.path.split("/assets/", 1)[-1]
        if ".." in filename or "/" in filename:
            self.send_error(403)
            return
        fpath = get_asset_dir() / filename
        if not fpath.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        import mimetypes
        ct, _ = mimetypes.guess_type(str(fpath))
        self.send_header("Content-Type", ct or "application/octet-stream")
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
        d, secs = divmod(secs, 86400)
        h, secs = divmod(secs, 3600)
        m = secs // 60
        if d:
            return f"{d}d {h}h {m}m"
        if h:
            return f"{h}h {m}m"
        return f"{m}m"
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


# --- Viewer-Loop (wie Head, aber mit Sync-Empfaenger) ---

def viewer_loop(instances, sync_rx):
    """Playback-Loop fuer den Slave — Tick-Counter-basiert, mit Master-Sync."""
    global _playlists, _playback_cfg, _playback_state

    playlists_local, _playback_cfg = load_playlists()
    _playlists = playlists_local

    # TickClock: eigene Clock starten, wird bei v3-Sync vom Master uebernommen
    tick_clock = TickClock()
    master_t0_applied = False
    logging.info("TickClock gestartet (T0=%.3f, warte auf Master-Sync)", tick_clock.t0)

    counters = {}       # monitor_id -> DisplayCounter
    playback_state = {}
    paused = set()
    force_next = set()
    last_disp_mtime = 0
    last_playlist_mtime = 0
    last_tick = -1
    last_master_t0 = None  # Letztes angewendetes Master-T0 (fuer Re-Sync-Erkennung)

    # Initiale Counter erstellen
    for inst in instances:
        pl = _playlists.get(inst.monitor_id, [])
        if pl:
            counters[inst.monitor_id] = DisplayCounter(pl)

    while True:
        # v3-Sync: T0 vom Master uebernehmen (initial + bei Aenderung/Neustart)
        if sync_rx.is_v3():
            master_t0 = sync_rx.get_master_t0()
            t0_changed = master_t0 and master_t0 != last_master_t0
            if t0_changed:
                local_tick, _ = sync_rx.get_local_tick()
                if local_tick is not None:
                    avg_off = sync_rx._avg_offset()
                    old_t0 = tick_clock.t0
                    tick_clock.t0 = master_t0 - avg_off
                    last_master_t0 = master_t0
                    if not master_t0_applied:
                        logging.info("TickClock synchronisiert (Master-T0=%.3f, lokal=%.3f)",
                                     master_t0, tick_clock.t0)
                        master_t0_applied = True
                    else:
                        logging.info("TickClock RE-SYNC (Master-T0=%.3f, alt=%.3f, neu=%.3f)",
                                     master_t0, old_t0, tick_clock.t0)
                    # Counter-State zuruecksetzen (Tick-Nummerierung hat sich geaendert)
                    for mid, counter in counters.items():
                        counter._last_tick = None

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
                if inst.monitor_id in counters:
                    counters[inst.monitor_id]._last_tick = None

        # Rotation live anwenden
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

        # Playlist aus persistenter Datei
        try:
            pl_mtime = PLAYLIST_FILE.stat().st_mtime
        except OSError:
            pl_mtime = 0

        if pl_mtime != last_playlist_mtime:
            last_playlist_mtime = pl_mtime
            old_playlists = dict(_playlists)
            playlists_local, _playback_cfg = load_playlists()
            _playlists = playlists_local
            for inst in instances:
                old_pl = old_playlists.get(inst.monitor_id, [])
                new_pl = playlists_local.get(inst.monitor_id, [])
                if new_pl != old_pl:
                    logging.info("[%s] Playlist: %d Assets", inst.monitor_id, len(new_pl))
                    counters[inst.monitor_id] = DisplayCounter(new_pl)
                elif new_pl and inst.monitor_id not in counters:
                    counters[inst.monitor_id] = DisplayCounter(new_pl)

        # Externe Befehle (next/prev)
        if COMMAND_FILE.exists():
            try:
                cmds = json.loads(COMMAND_FILE.read_text())
                COMMAND_FILE.unlink()
                if not isinstance(cmds, list):
                    cmds = [cmds]
                for cmd in cmds:
                    action = cmd.get("cmd", cmd.get("command", ""))
                    target = cmd.get("monitor", "")
                    for inst in instances:
                        if target and target != "all" and inst.monitor_id != target:
                            continue
                        counter = counters.get(inst.monitor_id)
                        if not counter or not counter.playlist:
                            continue
                        if action == "next":
                            force_next.add(inst.monitor_id)
                        elif action == "prev":
                            force_next.add(inst.monitor_id)
                            counter.force_prev()
                            counter.force_prev()
                        elif action in ("stop", "pause"):
                            paused.add(inst.monitor_id)
                        elif action == "play":
                            paused.discard(inst.monitor_id)
                        logging.info("[%s] Befehl: %s", inst.monitor_id, action)
            except Exception as e:
                logging.warning("Command-Datei Fehler: %s", e)

        # Tick-basierte Wechsellogik
        new_tick = current_tick != last_tick
        if new_tick:
            last_tick = current_tick

        pending_switches = []
        for inst in instances:
            counter = counters.get(inst.monitor_id)
            if not counter or not counter.playlist:
                continue

            # Force next/prev
            if inst.monitor_id in force_next:
                force_next.discard(inst.monitor_id)
                new_index = counter.force_next()
                pl = counter.playlist
                asset = pl[new_index]
                uri = asset.get("uri", "")
                name = asset.get("asset", "Unknown")
                local_path = cache_asset(uri, name)
                if local_path:
                    pending_switches.append((inst, local_path, name, new_index))
                    playback_state[inst.monitor_id] = {"index": new_index, "asset": name}
                continue

            if inst.monitor_id in paused:
                continue

            if not new_tick:
                continue

            # Shuffle
            shuffle = _playback_cfg.get(inst.monitor_id, {}).get("shuffle", False)
            if shuffle:
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
            uri = asset.get("uri", "")
            name = asset.get("asset", "Unknown")

            local_path = cache_asset(uri, name)
            if not local_path:
                logging.warning("[%s] Asset fehlt: %s", inst.monitor_id, name)
                counter.force_next()
                continue

            pending_switches.append((inst, local_path, name, new_index))
            playback_state[inst.monitor_id] = {"index": new_index, "asset": name}

        # Gleichzeitig wechseln
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
                logging.info("[%s] %s (idx %d)", inst.monitor_id, name, current_index)
                t = threading.Thread(target=sync_load, args=(inst, uri, current_index))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            _playback_state = dict(playback_state)
            write_playback_state(playback_state)

        # Sleep bis naechster Tick
        next_tick_hw = tick_clock.next_tick_hw()
        delta_to_tick = next_tick_hw - _hw_now()
        sleep_until = time.time() + min(delta_to_tick, 1.0)
        while time.time() < sleep_until - 0.02:
            if COMMAND_FILE.exists():
                break
            time.sleep(min(0.2, max(0, sleep_until - time.time() - 0.02)))
        if not COMMAND_FILE.exists():
            while _hw_now() < next_tick_hw:
                pass


# --- Main ---

def main():
    # Realtime-Scheduling fuer praezises Timing
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))
        logging.info("SCHED_FIFO aktiv (Prioritaet 1)")
    except PermissionError:
        logging.warning("SCHED_FIFO nicht verfuegbar (keine Berechtigung)")

    global _instances, _hostname, _monitor_ids

    _hostname = socket.gethostname()
    _monitor_ids = [f"{_hostname}-1", f"{_hostname}-2"]

    logging.info("Displaywall Agent gestartet: %s", _hostname)
    logging.info("Monitore: %s", _monitor_ids)
    logging.info("Asset-Verzeichnis: %s (USB: %s)", get_asset_dir(),
                 USB_MOUNT.is_mount())

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    # Display-Konfiguration laden
    disp_config = load_displays()

    # mpv-Instanzen starten
    instances = []
    for mid, connector in [(_monitor_ids[0], CONNECTOR_1),
                           (_monitor_ids[1], CONNECTOR_2)]:
        rotation = disp_config.get(connector, {}).get("rotation", 0)
        sock = f"/tmp/mpv-{mid}.sock"
        inst = MpvInstance(mid, connector, rotation, sock)
        if inst.start():
            instances.append(inst)
            logging.info("[%s] mpv laeuft", mid)
        else:
            logging.error("[%s] mpv-Start fehlgeschlagen", mid)
        time.sleep(2)

    _instances = instances

    if not instances:
        logging.error("Keine mpv-Instanz gestartet")
        sys.exit(1)

    logging.info("%d Display(s) aktiv", len(instances))

    # Sync-Empfaenger starten
    sync_rx = SyncReceiver()
    sync_rx.start()

    # Signal-Handler
    def handle_signal(sig, frame):
        logging.info("Signal %s — beende...", sig)
        sync_rx.stop()
        for inst in instances:
            inst.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Viewer-Loop in eigenem Thread (mit Crash-Recovery)
    def _viewer_loop_safe():
        while True:
            try:
                viewer_loop(instances, sync_rx)
            except Exception:
                logging.exception("viewer_loop CRASH — Neustart in 2s")
                time.sleep(2)

    viewer_thread = threading.Thread(target=_viewer_loop_safe, daemon=True)
    viewer_thread.start()

    # HTTP-Server (Hauptthread)
    server = HTTPServer(("0.0.0.0", AGENT_PORT), AgentHandler)
    logging.info("API lauscht auf Port %d", AGENT_PORT)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    handle_signal(signal.SIGTERM, None)


if __name__ == "__main__":
    main()
