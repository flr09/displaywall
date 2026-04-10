#!/usr/bin/env python3
"""Displaywall Manager — Web-GUI fuer Dual-Display-Verwaltung.

Leichtgewichtiger HTTP-Server (Python stdlib) auf Port 8080.
Verwaltet Asset-Zuweisung (Display 1 / Display 2) und Rotation.
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8080
DB_PATH = Path.home() / ".screenly" / "screenly.db"
DISPLAYS_JSON = Path.home() / ".screenly" / "displays.json"
PREFIX = "2:"

HTML_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Displaywall Manager</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }
  header { background: #16213e; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center;
           border-bottom: 2px solid #0f3460; }
  header h1 { font-size: 1.4rem; color: #e94560; }
  .status-bar { display: flex; gap: 1.5rem; font-size: 0.85rem; }
  .status-item { display: flex; align-items: center; gap: 0.4rem; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .dot.green { background: #4caf50; }
  .dot.red { background: #f44336; }
  .dot.yellow { background: #ff9800; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; padding: 1.5rem; max-width: 1400px; margin: 0 auto; }
  .display-panel { background: #16213e; border-radius: 12px; padding: 1.5rem; border: 1px solid #0f3460; }
  .display-panel h2 { font-size: 1.1rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; }
  .display-panel h2 .label { color: #e94560; }
  .rotation-select { background: #0f3460; color: #e0e0e0; border: 1px solid #1a1a2e; border-radius: 6px;
                      padding: 0.3rem 0.5rem; font-size: 0.85rem; }
  .asset-list { list-style: none; margin-top: 1rem; }
  .asset-item { display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem;
                background: #1a1a2e; margin-bottom: 0.5rem; border-radius: 8px; border: 1px solid #0f3460;
                transition: all 0.2s; }
  .asset-item:hover { border-color: #e94560; }
  .asset-info { flex: 1; min-width: 0; }
  .asset-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .asset-meta { font-size: 0.75rem; color: #888; margin-top: 0.2rem; }
  .asset-badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 10px; margin-left: 0.5rem;
                 text-transform: uppercase; }
  .badge-image { background: #1b5e20; color: #a5d6a7; }
  .badge-video { background: #4a148c; color: #ce93d8; }
  .badge-web { background: #e65100; color: #ffcc80; }
  .btn-move { background: #0f3460; color: #e0e0e0; border: 1px solid #e94560; border-radius: 6px;
              padding: 0.4rem 0.8rem; cursor: pointer; font-size: 0.8rem; white-space: nowrap; transition: all 0.2s; }
  .btn-move:hover { background: #e94560; color: white; }
  .empty-msg { text-align: center; color: #666; padding: 2rem; font-style: italic; }
  footer { text-align: center; padding: 1rem; font-size: 0.8rem; color: #555; }
  footer a { color: #e94560; text-decoration: none; }
  .reboot-hint { background: #e65100; color: white; padding: 0.5rem 1rem; border-radius: 6px;
                 text-align: center; margin: 0 1.5rem; font-size: 0.85rem; display: none; }
  .info-row { display: flex; gap: 1rem; font-size: 0.8rem; color: #888; margin-top: 0.3rem; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <h1>Displaywall Manager</h1>
  <div class="status-bar" id="statusBar">
    <div class="status-item"><span class="dot" id="dotViewer1"></span> Viewer 1</div>
    <div class="status-item"><span class="dot" id="dotViewer2"></span> Viewer 2</div>
    <div class="status-item" id="tempItem"></div>
  </div>
</header>

<div class="reboot-hint" id="rebootHint">Rotation geaendert — Reboot noetig fuer Kernel-Rotation. Viewer-2 wird sofort aktualisiert.</div>

<main>
  <div class="display-panel">
    <h2>
      <span><span class="label">HDMI-1</span> — Display 1</span>
      <select class="rotation-select" data-output="HDMI-A-1" onchange="setRotation(this)">
        <option value="0">0° Landscape</option>
        <option value="90">90° Portrait</option>
        <option value="180">180°</option>
        <option value="270">270° Portrait</option>
      </select>
    </h2>
    <div class="info-row" id="info1"></div>
    <ul class="asset-list" id="list1"></ul>
  </div>
  <div class="display-panel">
    <h2>
      <span><span class="label">HDMI-2</span> — Display 2</span>
      <select class="rotation-select" data-output="HDMI-A-2" onchange="setRotation(this)">
        <option value="0">0° Landscape</option>
        <option value="90">90° Portrait</option>
        <option value="180">180°</option>
        <option value="270">270° Portrait</option>
      </select>
    </h2>
    <div class="info-row" id="info2"></div>
    <ul class="asset-list" id="list2"></ul>
  </div>
</main>

<footer>
  <a href="http://__HOST__:80" target="_blank">Anthias UI (Asset-Upload)</a> &middot;
  Displaywall Manager v1.0
</footer>

<script>
const PREFIX = '2:';
let assets = [];
let displays = {};

async function loadData() {
  try {
    const [aRes, dRes, sRes] = await Promise.all([
      fetch('/api/assets'), fetch('/api/displays'), fetch('/api/status')
    ]);
    assets = await aRes.json();
    displays = await dRes.json();
    const status = await sRes.json();
    render(status);
  } catch(e) { console.error(e); }
}

function badgeClass(mime) {
  if (mime.includes('image')) return 'badge-image';
  if (mime.includes('video')) return 'badge-video';
  return 'badge-web';
}

function badgeLabel(mime) {
  if (mime.includes('image')) return 'Bild';
  if (mime.includes('video')) return 'Video';
  return 'Web';
}

function render(status) {
  const list1 = document.getElementById('list1');
  const list2 = document.getElementById('list2');
  list1.innerHTML = '';
  list2.innerHTML = '';

  const d1 = [], d2 = [];
  assets.forEach(a => {
    if (a.name.startsWith(PREFIX)) d2.push(a);
    else d1.push(a);
  });

  function renderList(el, items, targetDisplay) {
    if (!items.length) {
      el.innerHTML = '<li class="empty-msg">Keine Assets zugewiesen</li>';
      return;
    }
    items.forEach(a => {
      const displayName = a.name.startsWith(PREFIX) ? a.name.slice(PREFIX.length) : a.name;
      const btnLabel = targetDisplay === 2 ? '→ Display 2' : '← Display 1';
      const enabled = a.is_enabled ? '' : ' (deaktiviert)';
      el.innerHTML += '<li class="asset-item">' +
        '<div class="asset-info">' +
          '<div class="asset-name">' + escHtml(displayName) + enabled +
            '<span class="asset-badge ' + badgeClass(a.mimetype) + '">' + badgeLabel(a.mimetype) + '</span></div>' +
          '<div class="asset-meta">' + a.duration + 's &middot; Order: ' + a.play_order + '</div>' +
        '</div>' +
        '<button class="btn-move" onclick="moveAsset(\'' + a.asset_id + '\',' + targetDisplay + ')">' + btnLabel + '</button>' +
      '</li>';
    });
  }

  renderList(list1, d1, 2);
  renderList(list2, d2, 1);

  // Rotation Selects
  document.querySelectorAll('.rotation-select').forEach(sel => {
    const output = sel.dataset.output;
    const rot = (displays[output] || {}).rotation || 0;
    sel.value = rot;
  });

  // Status
  const d1dot = document.getElementById('dotViewer1');
  const d2dot = document.getElementById('dotViewer2');
  d1dot.className = 'dot ' + (status.viewer1_running ? 'green' : 'red');
  d2dot.className = 'dot ' + (status.viewer2_running ? 'green' : 'red');
  document.getElementById('tempItem').textContent = status.temperature || '';

  document.getElementById('info1').textContent = d1.filter(a => a.is_enabled).length + ' aktive Assets';
  document.getElementById('info2').textContent = d2.filter(a => a.is_enabled).length + ' aktive Assets';
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function moveAsset(id, target) {
  await fetch('/api/move', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({asset_id: id, target: target})
  });
  loadData();
}

async function setRotation(sel) {
  const output = sel.dataset.output;
  const rotation = parseInt(sel.value);
  await fetch('/api/rotation', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({output: output, rotation: rotation})
  });
  document.getElementById('rebootHint').style.display = 'block';
  loadData();
}

loadData();
setInterval(loadData, 5000);
</script>
</body>
</html>"""


def load_displays():
    try:
        with open(DISPLAYS_JSON) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        default = {
            "HDMI-A-1": {"rotation": 0, "resolution": "2560x1440"},
            "HDMI-A-2": {"rotation": 0, "resolution": "2560x1440"},
        }
        save_displays(default)
        return default


def save_displays(data):
    DISPLAYS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DISPLAYS_JSON, "w") as f:
        json.dump(data, f, indent=2)


def get_assets():
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT asset_id, name, uri, mimetype, duration, is_enabled, play_order "
            "FROM assets ORDER BY play_order ASC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def move_asset(asset_id, target):
    """Setzt oder entfernt das '2:' Prefix im Asset-Namen."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT name FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False

        name = row[0]
        if target == 2 and not name.startswith(PREFIX):
            new_name = PREFIX + name
        elif target == 1 and name.startswith(PREFIX):
            new_name = name[len(PREFIX):]
        else:
            conn.close()
            return True

        conn.execute(
            "UPDATE assets SET name = ? WHERE asset_id = ?",
            (new_name, asset_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def get_status():
    status = {"viewer1_running": False, "viewer2_running": False, "temperature": ""}

    # Viewer 1 (Docker)
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "screenly-anthias-viewer-1"],
            capture_output=True, text=True, timeout=3,
        )
        status["viewer1_running"] = r.stdout.strip() == "true"
    except Exception:
        pass

    # Viewer 2 (systemd)
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "anthias-viewer2"],
            capture_output=True, text=True, timeout=3,
        )
        status["viewer2_running"] = r.stdout.strip() == "active"
    except Exception:
        pass

    # Temperatur
    try:
        r = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=3,
        )
        status["temperature"] = r.stdout.strip()
    except Exception:
        pass

    return status


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Stille Logs

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        host = self.headers.get("Host", "localhost:8080").split(":")[0]
        body = html.replace("__HOST__", host).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "":
            self._send_html(HTML_PAGE)
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
    # Default displays.json anlegen falls nicht vorhanden
    load_displays()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Displaywall Manager laeuft auf Port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
