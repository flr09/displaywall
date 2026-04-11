/* Displaywall VJ-Manager — Canvas-Editor (Fabric.js) */

let canvas;
let wallConfig = null;
let selectedMonitor = null;

const CANVAS_SCALE = 0.1;  // 8000px Canvas → 800px im Browser
const MONITOR_COLORS = {
  'head-1': '#e94560', 'head-2': '#ff6b6b',
  'slave1-1': '#4ecdc4', 'slave1-2': '#45b7aa',
  'slave2-1': '#f9ca24', 'slave2-2': '#f0b800',
};
const MONITOR_BORDER_SELECTED = '#ffffff';

function initCanvas() {
  canvas = new fabric.Canvas('wallCanvas', {
    width: 860,
    height: 340,
    backgroundColor: '#0a0a1a',
    selection: false,
  });

  canvas.on('object:modified', onMonitorMoved);
  canvas.on('object:selected', onMonitorSelected);
  canvas.on('selection:created', onMonitorSelected);
  canvas.on('selection:updated', onMonitorSelected);
  canvas.on('selection:cleared', onMonitorDeselected);
}

function renderCanvas() {
  if (!wallConfig || !canvas) return;
  canvas.clear();

  var monitors = wallConfig.canvas.monitors;
  monitors.forEach(function (mon) {
    var w = mon.width * CANVAS_SCALE;
    var h = mon.height * CANVAS_SCALE;
    var color = MONITOR_COLORS[mon.id] || '#666';

    // Playlist-Zaehler
    var pl = (wallConfig.playlists || {})[mon.id] || [];

    var rect = new fabric.Rect({
      width: w,
      height: h,
      fill: color,
      opacity: 0.3,
      stroke: color,
      strokeWidth: 2,
      rx: 4,
      ry: 4,
    });

    var label = new fabric.Text(mon.label || mon.id, {
      fontSize: 12,
      fill: '#fff',
      fontFamily: 'system-ui, sans-serif',
      originX: 'center',
      originY: 'center',
      left: w / 2,
      top: h / 2 - 8,
    });

    var info = new fabric.Text(
      mon.output + (mon.rotation ? ' ' + mon.rotation + '\u00b0' : '') +
      '\n' + pl.length + ' Assets',
      {
        fontSize: 9,
        fill: '#aaa',
        fontFamily: 'system-ui, sans-serif',
        originX: 'center',
        originY: 'center',
        left: w / 2,
        top: h / 2 + 10,
        textAlign: 'center',
      }
    );

    var group = new fabric.Group([rect, label, info], {
      left: mon.x * CANVAS_SCALE + 10,
      top: mon.y * CANVAS_SCALE + 10,
      hasControls: false,
      hasBorders: true,
      borderColor: MONITOR_BORDER_SELECTED,
      monitorId: mon.id,
    });

    if (mon.rotation === 90 || mon.rotation === 270) {
      // Swap visual dimensions for portrait
      rect.set({ width: h, height: w });
      label.set({ left: h / 2, top: w / 2 - 8 });
      info.set({ left: h / 2, top: w / 2 + 10 });
      group.set({
        width: h,
        height: w,
      });
    }

    canvas.add(group);
  });

  canvas.renderAll();
}

function onMonitorMoved(e) {
  var obj = e.target;
  if (!obj || !obj.monitorId) return;

  var mon = findMonitor(obj.monitorId);
  if (!mon) return;

  mon.x = Math.round((obj.left - 10) / CANVAS_SCALE);
  mon.y = Math.round((obj.top - 10) / CANVAS_SCALE);

  saveWallConfig();
}

function onMonitorSelected(e) {
  var obj = e.selected ? e.selected[0] : e.target;
  if (!obj || !obj.monitorId) return;

  selectedMonitor = obj.monitorId;
  renderPlaylistPanel(selectedMonitor);
  document.getElementById('playlistPanel').style.display = 'block';
}

function onMonitorDeselected() {
  selectedMonitor = null;
  document.getElementById('playlistPanel').style.display = 'none';
}

function findMonitor(id) {
  if (!wallConfig) return null;
  var monitors = wallConfig.canvas.monitors;
  for (var i = 0; i < monitors.length; i++) {
    if (monitors[i].id === id) return monitors[i];
  }
  return null;
}

/* --- Playlist-Panel --- */

function renderPlaylistPanel(monitorId) {
  var mon = findMonitor(monitorId);
  if (!mon) return;

  document.getElementById('playlistTitle').textContent =
    (mon.label || mon.id) + ' (' + mon.output + ')';

  var rotSel = document.getElementById('monitorRotation');
  rotSel.value = mon.rotation || 0;
  rotSel.dataset.monitorId = monitorId;

  var playlist = (wallConfig.playlists || {})[monitorId] || [];
  var list = document.getElementById('playlistItems');
  list.innerHTML = '';

  if (!playlist.length) {
    list.innerHTML = '<li class="empty-msg">Keine Assets zugewiesen. Assets aus dem Pool hierher ziehen.</li>';
    return;
  }

  playlist.forEach(function (item, idx) {
    var li = document.createElement('li');
    li.className = 'playlist-item';
    li.draggable = true;
    li.dataset.idx = idx;

    li.innerHTML =
      '<span class="playlist-name">' + escHtml(item.asset) + '</span>' +
      '<span class="playlist-dur">' + (item.duration || 'auto') + 's</span>' +
      '<button class="btn-remove" onclick="removeFromPlaylist(\'' +
        monitorId + '\',' + idx + ')">\u00d7</button>';

    // Drag&Drop fuer Sortierung
    li.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/plain', 'reorder:' + idx);
    });
    li.addEventListener('dragover', function (e) { e.preventDefault(); });
    li.addEventListener('drop', function (e) {
      e.preventDefault();
      var data = e.dataTransfer.getData('text/plain');
      if (data.startsWith('reorder:')) {
        var fromIdx = parseInt(data.split(':')[1], 10);
        reorderPlaylist(monitorId, fromIdx, idx);
      }
    });

    list.appendChild(li);
  });
}

function removeFromPlaylist(monitorId, idx) {
  var playlist = (wallConfig.playlists || {})[monitorId] || [];
  playlist.splice(idx, 1);
  wallConfig.playlists[monitorId] = playlist;
  savePlaylist(monitorId);
  renderPlaylistPanel(monitorId);
  renderCanvas();
}

function reorderPlaylist(monitorId, fromIdx, toIdx) {
  var playlist = (wallConfig.playlists || {})[monitorId] || [];
  var item = playlist.splice(fromIdx, 1)[0];
  playlist.splice(toIdx, 0, item);
  wallConfig.playlists[monitorId] = playlist;
  savePlaylist(monitorId);
  renderPlaylistPanel(monitorId);
}

function setMonitorRotation(sel) {
  var monitorId = sel.dataset.monitorId;
  var rotation = parseInt(sel.value, 10);
  var mon = findMonitor(monitorId);
  if (!mon) return;
  mon.rotation = rotation;
  saveWallConfig();
  renderCanvas();
}

/* --- Pool-Panel --- */

function renderPool(assets) {
  var list = document.getElementById('poolList');
  list.innerHTML = '';

  if (!assets || !assets.length) {
    list.innerHTML = '<li class="empty-msg">Keine Assets vorhanden. Upload ueber Anthias UI.</li>';
    return;
  }

  assets.forEach(function (a) {
    var name = a.name.replace(/^2:/, '');
    var li = document.createElement('li');
    li.className = 'pool-item';
    li.draggable = true;

    li.innerHTML =
      '<span class="pool-name">' + escHtml(name) + '</span>' +
      '<span class="asset-badge ' + badgeClass(a.mimetype) + '">' +
        badgeLabel(a.mimetype) + '</span>' +
      '<span class="pool-dur">' + a.duration + 's</span>';

    li.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/plain', 'pool:' + name + ':' + a.duration + ':' + a.uri);
    });

    list.appendChild(li);
  });
}

/* --- Drop-Zone fuer Playlist --- */

function initPlaylistDrop() {
  var zone = document.getElementById('playlistItems');

  zone.addEventListener('dragover', function (e) {
    e.preventDefault();
    zone.classList.add('drop-active');
  });

  zone.addEventListener('dragleave', function () {
    zone.classList.remove('drop-active');
  });

  zone.addEventListener('drop', function (e) {
    e.preventDefault();
    zone.classList.remove('drop-active');

    var data = e.dataTransfer.getData('text/plain');
    if (!data.startsWith('pool:') || !selectedMonitor) return;

    var parts = data.split(':');
    var assetName = parts[1];
    var duration = parseInt(parts[2], 10) || 10;
    var uri = parts.slice(3).join(':');

    if (!wallConfig.playlists) wallConfig.playlists = {};
    if (!wallConfig.playlists[selectedMonitor]) wallConfig.playlists[selectedMonitor] = [];

    wallConfig.playlists[selectedMonitor].push({
      asset: assetName,
      duration: duration,
      uri: uri,
    });

    savePlaylist(selectedMonitor);
    renderPlaylistPanel(selectedMonitor);
    renderCanvas();
  });
}

/* --- API-Kommunikation --- */

async function loadWallConfig() {
  try {
    var res = await fetch('/api/wall');
    wallConfig = await res.json();
    renderCanvas();
  } catch (e) {
    console.error('Fehler beim Laden der Wall-Config:', e);
  }
}

async function saveWallConfig() {
  try {
    await fetch('/api/wall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(wallConfig),
    });
  } catch (e) {
    console.error('Fehler beim Speichern:', e);
  }
}

async function savePlaylist(monitorId) {
  try {
    await fetch('/api/playlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        output: monitorId,
        playlist: wallConfig.playlists[monitorId] || [],
      }),
    });
  } catch (e) {
    console.error('Fehler beim Speichern der Playlist:', e);
  }
}
