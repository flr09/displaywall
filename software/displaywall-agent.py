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
    if local_path.is_file():
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
        return str(local_path)
    except Exception as e:
        logging.error("Download fehlgeschlagen: %s — %s", url, e)
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

    def __init__(self, monitor_id, connector):
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

    def update_playlist(self, items, shuffle=False):
        with self._lock:
            self.playlist = list(items)
            self.shuffle = shuffle
            if self.index >= len(self.playlist):
                self.index = 0
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
            if not self.playlist:
                return
            self.index = (self.index + direction) % len(self.playlist)
        # Aktuellen mpv-Prozess beenden, naechstes Asset startet automatisch
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def get_state(self):
        return {
            "monitor": self.monitor_id,
            "connector": self.connector,
            "index": self.index,
            "asset": self.current_asset,
            "playlist_length": len(self.playlist),
            "running": self.running,
        }

    def run(self):
        rotation = load_displays().get(self.connector, {}).get("rotation", 0)

        while self.running:
            with self._lock:
                pl = list(self.playlist)
                shuffle = self.shuffle

            if not pl:
                time.sleep(3)
                continue

            if shuffle:
                self.index = random.randint(0, len(pl) - 1)

            item = pl[self.index]
            self.current_asset = item.get("asset", "")

            # Asset lokal sicherstellen
            uri = item.get("uri", "")
            local_path = cache_asset(uri, self.current_asset)
            if not local_path:
                logging.warning("[%s] Asset nicht verfuegbar: %s", self.monitor_id, uri)
                self.index = (self.index + 1) % len(pl)
                time.sleep(2)
                continue

            # Playback-State schreiben
            write_playback_state(self.monitor_id, self.index, self.current_asset)

            # Typ erkennen
            lower = local_path.lower()
            is_image = any(lower.endswith(ext) for ext in
                          (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"))
            is_video = any(lower.endswith(ext) for ext in
                          (".mp4", ".webm", ".mov", ".avi", ".mkv"))

            duration = int(item.get("duration", 10))

            cmd = [
                "mpv", "--no-terminal",
                "--vo=gpu", "--gpu-context=drm",
                f"--drm-connector={self.connector}",
            ]

            if rotation:
                cmd.append(f"--video-rotate={rotation}")

            if is_image:
                cmd.extend([f"--image-display-duration={duration}", "--loop-file=no"])
                logging.info("[%s] Bild: %s (%ds)", self.monitor_id, self.current_asset, duration)
            elif is_video:
                logging.info("[%s] Video: %s", self.monitor_id, self.current_asset)
            else:
                logging.warning("[%s] Unbekannter Typ: %s", self.monitor_id, local_path)
                self.index = (self.index + 1) % len(pl)
                continue

            cmd.extend(["--", local_path])

            try:
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.process.wait()

                if not self.running:
                    break
            except Exception as e:
                logging.error("[%s] mpv-Fehler: %s", self.monitor_id, e)
                time.sleep(3)
            finally:
                self.process = None

            if not shuffle:
                with self._lock:
                    self.index = (self.index + 1) % len(pl) if pl else 0


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

        status = {
            "hostname": hostname,
            "ip": _get_ip(),
            "temperature": temp,
            "throttle": throttle.split("=")[-1] if "=" in throttle else throttle,
            "disk": get_disk_info(),
            "viewers": {vid: viewers[vid].get_state() for vid in viewers},
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


def start_viewer(monitor_id):
    """Viewer-Thread fuer einen Monitor starten."""
    connector = CONNECTOR_1 if monitor_id.endswith("-1") else CONNECTOR_2
    vt = ViewerThread(monitor_id, connector)
    viewers[monitor_id] = vt

    # Gespeicherte Playlist laden falls vorhanden
    if monitor_id in playlists:
        shuffle = playback_cfg.get(monitor_id, {}).get("shuffle", False)
        vt.update_playlist(playlists[monitor_id], shuffle)

    vt.start()
    logging.info("Viewer gestartet: %s auf %s", monitor_id, connector)


# --- Main ---

def main():
    global hostname, monitor_ids

    hostname = get_hostname()
    monitor_ids = get_monitor_ids()

    logging.info("Displaywall Agent gestartet: %s", hostname)
    logging.info("Monitore: %s", monitor_ids)
    logging.info("Asset-Verzeichnis: %s (USB: %s)", get_asset_dir(), USB_MOUNT.is_mount())

    # Verzeichnisse anlegen
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    # Gespeicherte Playlists laden
    load_playlists()

    # Viewer-Threads starten
    for mid in monitor_ids:
        start_viewer(mid)

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
