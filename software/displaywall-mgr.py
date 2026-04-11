#!/usr/bin/env python3
"""Displaywall Manager — Web-Server.

HTTP-Server auf Port 8080. Liefert die Web-GUI (statische Dateien)
und die REST-API fuer Asset-Verwaltung und Display-Konfiguration.
"""

import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from displaywall.config import WEBUI_PORT, load_displays, save_displays
from displaywall.db import get_assets, move_asset
from displaywall.status import get_status

WEBUI_DIR = Path(__file__).parent / "webui"


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

        # API
        elif path == "/api/assets":
            self._send_json(get_assets())
        elif path == "/api/displays":
            self._send_json(load_displays())
        elif path == "/api/status":
            self._send_json(get_status())
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
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

        else:
            self.send_error(404)


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
