#!/usr/bin/env python3
"""Displaywall Manager — Web-Server.

HTTP-Server auf Port 8080. Liefert die Web-GUI (statische Dateien)
und die REST-API fuer Asset-Verwaltung und Display-Konfiguration.
"""

import json
import mimetypes
import re
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from displaywall.config import WEBUI_PORT, ASSET_DIR, load_displays, save_displays
from displaywall.db import get_assets, move_asset, add_asset
from displaywall.status import get_status
from displaywall.wall import (
    load_wall_config,
    save_wall_config,
    set_playlist,
    update_monitor,
)

WEBUI_DIR = Path(__file__).parent / "webui"
PLAYBACK_STATE_FILE = Path(__file__).parent / "displaywall" / "playback_state.json"


def _read_playback_state():
    """Liest den Playback-Status aller Viewer (welcher Index gerade spielt)."""
    try:
        if PLAYBACK_STATE_FILE.is_file():
            return json.loads(PLAYBACK_STATE_FILE.read_text())
    except Exception:
        pass
    return {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    # --- Response-Helfer ---

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath):
        if not filepath.is_file():
            self.send_error(404)
            return
        content_type, _ = mimetypes.guess_type(str(filepath))
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # --- Routing ---

    def do_GET(self):
        path = urlparse(self.path).path

        # Statische Dateien
        if path == "/" or path == "":
            self._send_file(WEBUI_DIR / "index.html")
        elif path.startswith("/static/"):
            filename = path[len("/static/"):]
            # Pfad-Traversal verhindern
            safe_path = (WEBUI_DIR / filename).resolve()
            if safe_path.is_relative_to(WEBUI_DIR):
                self._send_file(safe_path)
            else:
                self.send_error(403)

        # Asset-Dateien (Bilder/Videos fuer Preview)
        elif path.startswith("/assets/"):
            filename = path[len("/assets/"):]
            safe_path = (ASSET_DIR / filename).resolve()
            if safe_path.is_relative_to(ASSET_DIR):
                self._send_file(safe_path)
            else:
                self.send_error(403)

        # API
        elif path == "/api/assets":
            self._send_json(get_assets())
        elif path == "/api/displays":
            self._send_json(load_displays())
        elif path == "/api/status":
            self._send_json(get_status())
        elif path == "/api/wall":
            self._send_json(load_wall_config())
        elif path == "/api/pool":
            self._send_json(get_assets())
        elif path == "/api/playback":
            self._send_json(_read_playback_state())

        # --- Provisioning ---
        elif path == "/api/provision":
            self._handle_provision()
        elif path == "/api/provision/agent":
            self._send_file(Path(__file__).parent / "displaywall-agent.py")
        elif path == "/api/provision/setup":
            self._send_file(Path(__file__).parent / "setup-slave.sh")

        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/upload":
            self._handle_upload()
            return

        data = self._read_body()

        if path == "/api/move":
            ok = move_asset(data.get("asset_id"), data.get("target"))
            self._send_json({"ok": ok})

        elif path == "/api/rotation":
            displays = load_displays()
            output = data.get("output")
            rotation = data.get("rotation", 0)
            if output in displays:
                displays[output]["rotation"] = rotation
                save_displays(displays)
            self._send_json({"ok": True})

        elif path == "/api/wall":
            save_wall_config(data)
            self._send_json({"ok": True})

        elif path == "/api/playlist":
            output_id = data.get("output")
            playlist = data.get("playlist", [])
            ok = set_playlist(output_id, playlist)
            self._send_json({"ok": ok})

        elif path == "/api/monitor":
            monitor_id = data.get("id")
            updates = data.get("updates", {})
            ok = update_monitor(monitor_id, updates)
            self._send_json({"ok": ok})

        else:
            self.send_error(404)

    def _handle_upload(self):
        """Datei-Upload: speichert in ASSET_DIR, traegt in DB ein."""
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if "multipart/form-data" not in content_type:
            self._send_json({"ok": False, "error": "multipart erwartet"}, 400)
            return

        body = self.rfile.read(content_length)

        # Boundary extrahieren
        m = re.search(r"boundary=([^\s;]+)", content_type)
        if not m:
            self._send_json({"ok": False, "error": "Kein boundary"}, 400)
            return
        boundary = m.group(1).encode()

        # Multipart manuell parsen
        parts = {}
        chunks = body.split(b"--" + boundary)
        for part in chunks:
            if b"Content-Disposition" not in part:
                continue
            header, _, payload = part.partition(b"\r\n\r\n")
            # Payload endet mit \r\n vor dem naechsten boundary
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]

            name_m = re.search(rb'name="([^"]+)"', header)
            if not name_m:
                continue
            name = name_m.group(1).decode()

            fname_m = re.search(rb'filename="([^"]+)"', header)
            if fname_m:
                parts[name] = {"data": payload, "filename": fname_m.group(1).decode()}
            else:
                parts[name] = {"data": payload.decode(errors="replace")}

        file_part = parts.get("file")
        if not file_part or "data" not in file_part:
            self._send_json({"ok": False, "error": "Keine Datei"}, 400)
            return

        file_data = file_part["data"]
        filename = file_part.get("filename", "upload")
        duration = parts.get("duration", {}).get("data", "10")

        # MIME-Type bestimmen
        mime, _ = mimetypes.guess_type(filename)
        if not mime:
            mime = "application/octet-stream"

        # Datei speichern
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        asset_id = str(uuid.uuid4())
        ext = Path(filename).suffix
        dest = ASSET_DIR / (asset_id + ext)
        dest.write_bytes(file_data)

        # In DB eintragen
        uri = str(dest)
        ok = add_asset(asset_id, filename, uri, mime, int(duration))
        self._send_json({"ok": ok, "asset_id": asset_id, "name": filename})


    def _handle_provision(self):
        """Provisioning-Info: Was muss ein neuer Slave wissen?"""
        import socket
        head_ip = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            head_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        # Naechsten freien Slave-Hostnamen ermitteln
        wc = load_wall_config()
        monitors = wc.get("canvas", {}).get("monitors", [])
        used = set()
        for m in monitors:
            mid = m.get("id", "")
            if mid.startswith("slave"):
                used.add(mid.split("-")[0])

        # Registrierte Slaves aus bekannten Geraeten
        known_slaves = sorted(used)

        info = {
            "head_ip": head_ip,
            "head_port": WEBUI_PORT,
            "setup_url": f"http://{head_ip}:{WEBUI_PORT}/api/provision/setup",
            "agent_url": f"http://{head_ip}:{WEBUI_PORT}/api/provision/agent",
            "known_slaves": known_slaves,
            "wall_config": wc,
            "instructions": (
                "1. curl -sL /api/provision/setup -o setup-slave.sh\n"
                "2. curl -sL /api/provision/agent -o displaywall-agent.py\n"
                "3. sudo SLAVE_HOSTNAME=<name> HEAD_PI_IP=<ip> bash setup-slave.sh\n"
                "4. sudo reboot"
            ),
        }
        self._send_json(info)


def main():
    load_displays()
    server = HTTPServer(("0.0.0.0", WEBUI_PORT), Handler)
    print(f"Displaywall Manager auf Port {WEBUI_PORT}")
    print(f"Web-UI: {WEBUI_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
