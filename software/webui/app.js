/* Displaywall VJ-Manager — App-Logik */

var assets = [];
var wallConfig = null;
var selectedMonitor = null;

/* ============================================
   TAB-NAVIGATION
   ============================================ */

document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');

    var tabId = btn.dataset.tab;
    var color = document.getElementById(tabId).dataset.color;

    document.querySelectorAll('.tab-content').forEach(function (tc) { tc.classList.remove('active'); });
    document.getElementById(tabId).classList.add('active');

    var h1 = document.querySelector('#' + tabId + ' h1');
    if (h1) h1.style.color = color;

    // Canvas neu zeichnen wenn Tab sichtbar wird
    if (tabId === 'tabCanvas') {
      setTimeout(function () { resizeCanvas(); renderCanvas(); }, 50);
    }
  });
});

// Initiale Farbe
(function () {
  var first = document.querySelector('.tab-content.active');
  if (first) {
    var h1 = first.querySelector('h1');
    if (h1) h1.style.color = first.dataset.color;
  }
})();

/* ============================================
   OUTPUT
   ============================================ */

function showOutput(msg) {
  document.getElementById('outputText').textContent = msg;
}

/* ============================================
   DATEN LADEN
   ============================================ */

async function loadAssets() {
  try {
    var res = await fetch('/api/assets');
    assets = await res.json();
    renderPool();
  } catch (e) {
    showOutput('Fehler: ' + e.message);
  }
}

async function loadWallConfig() {
  try {
    var res = await fetch('/api/wall');
    wallConfig = await res.json();
    // Canvas init braucht wallConfig
    setTimeout(function () {
      resizeCanvas();
      renderCanvas();
    }, 100);
    renderMonitorSelector();
    renderDisplaySettings();
    renderSyncOffsets();
    if (selectedMonitor) renderPlaylist(selectedMonitor);
  } catch (e) {
    showOutput('Fehler: ' + e.message);
  }
}

async function loadStatus() {
  try {
    var res = await fetch('/api/status');
    var status = await res.json();
    renderStatus(status);
    updateToolbarStatus(status);
  } catch (e) { /* still */ }
}

async function saveWallConfig() {
  try {
    await fetch('/api/wall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(wallConfig),
    });
    showOutput('Gespeichert');
  } catch (e) {
    showOutput('Fehler: ' + e.message);
  }
}

async function savePlaylist(monitorId) {
  try {
    await fetch('/api/playlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        output: monitorId,
        playlist: (wallConfig.playlists || {})[monitorId] || [],
      }),
    });
    showOutput('Playlist gespeichert: ' + monitorId);
    flashSaveIndicator();
  } catch (e) {
    showOutput('Fehler: ' + e.message);
  }
}

function toggleShuffle() {
  if (!selectedMonitor || !wallConfig) {
    showOutput('Erst einen Monitor auswaehlen');
    return;
  }
  var pl = (wallConfig.playlists || {})[selectedMonitor];
  if (!pl) return;

  // shuffle Flag pro Playlist toggeln
  // Gespeichert als Property auf der Playlist-Ebene in wallConfig
  if (!wallConfig.playback) wallConfig.playback = {};
  var current = (wallConfig.playback[selectedMonitor] || {}).shuffle || false;
  if (!wallConfig.playback[selectedMonitor]) wallConfig.playback[selectedMonitor] = {};
  wallConfig.playback[selectedMonitor].shuffle = !current;

  saveWallConfig();
  updateShuffleBtn();
  showOutput('Zufall ' + (!current ? 'AN' : 'AUS') + ': ' + selectedMonitor);
}

function updateShuffleBtn() {
  var btn = document.getElementById('shuffleBtn');
  if (!btn || !selectedMonitor || !wallConfig) return;
  var active = wallConfig.playback &&
    wallConfig.playback[selectedMonitor] &&
    wallConfig.playback[selectedMonitor].shuffle;
  btn.classList.toggle('active', !!active);
}

function flashSaveIndicator() {
  var el = document.getElementById('saveIndicator');
  if (!el) return;
  el.textContent = '\u2713 Gespeichert';
  el.classList.add('visible');
  setTimeout(function () { el.classList.remove('visible'); }, 2000);
}

/* ============================================
   POOL (Sidebar — immer sichtbar)
   ============================================ */

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
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

function renderPool() {
  var list = document.getElementById('poolList');
  list.innerHTML = '';

  document.getElementById('poolCount').textContent = assets.length + ' Assets';

  if (!assets.length) {
    list.innerHTML = '<div class="empty-hint">Keine Assets.<br>Upload ueber Anthias UI.</div>';
    return;
  }

  assets.forEach(function (a) {
    var name = a.name.replace(/^2:/, '');
    var div = document.createElement('div');
    div.className = 'pool-item';
    div.draggable = true;

    div.innerHTML =
      '<div class="pool-item-name">' + escHtml(name) + '</div>' +
      '<div class="pool-item-meta">' +
        '<span class="badge ' + badgeClass(a.mimetype) + '">' + badgeLabel(a.mimetype) + '</span>' +
        '<span>' + a.duration + 's</span>' +
      '</div>';

    // Preview-Tooltip bei Mouseover
    if (a.mimetype && a.mimetype.includes('image')) {
      div.addEventListener('mouseenter', function (e) {
        showPreviewTooltip(assetUrl(a.uri), 'image', e);
      });
      div.addEventListener('mousemove', positionTooltip);
      div.addEventListener('mouseleave', hidePreviewTooltip);
    } else if (a.mimetype && a.mimetype.includes('video')) {
      div.addEventListener('mouseenter', function (e) {
        showPreviewTooltip(assetUrl(a.uri), 'video', e);
      });
      div.addEventListener('mousemove', positionTooltip);
      div.addEventListener('mouseleave', hidePreviewTooltip);
    }

    div.addEventListener('dragstart', function (e) {
      hidePreviewTooltip();
      e.dataTransfer.setData('text/plain', JSON.stringify({
        type: 'pool',
        name: name,
        duration: a.duration,
        uri: a.uri,
        mimetype: a.mimetype,
      }));
      div.style.opacity = '0.4';
    });

    div.addEventListener('dragend', function () {
      div.style.opacity = '1';
    });

    list.appendChild(div);
  });
}

/* ============================================
   MONITOR SELECTOR
   ============================================ */

var MONITOR_COLORS = {
  'head-1': '#e94560', 'head-2': '#ff6b6b',
  'slave1-1': '#4ecdc4', 'slave1-2': '#45b7aa',
  'slave2-1': '#f9ca24', 'slave2-2': '#f0b800',
};

function renderMonitorSelector() {
  var cont = document.getElementById('monitorSelector');
  cont.innerHTML = '';
  if (!wallConfig) return;

  wallConfig.canvas.monitors.forEach(function (mon) {
    var btn = document.createElement('button');
    btn.className = 'mon-btn' + (selectedMonitor === mon.id ? ' active' : '');
    btn.textContent = mon.label || mon.id;
    var col = MONITOR_COLORS[mon.id] || '#555';
    btn.style.borderColor = col;
    if (selectedMonitor === mon.id) {
      btn.style.background = col;
      btn.style.borderColor = col;
    }
    btn.addEventListener('click', function () { selectMonitor(mon.id); });
    cont.appendChild(btn);
  });
}

function selectMonitor(id) {
  selectedMonitor = id;
  renderMonitorSelector();
  renderPlaylist(id);
  renderCanvas();

  // Snapshot aktualisieren wenn im Select-Modus (Canvas versteckt)
  if (canvasMode === 'select' && snapshotDataUrl) {
    updateSnapshotHighlight();
  }

  var mon = findMonitor(id);
  if (mon) {
    document.getElementById('playlistTitle').textContent =
      'Playlist \u2014 ' + (mon.label || mon.id);
  }
  updateShuffleBtn();
}

function findMonitor(id) {
  if (!wallConfig) return null;
  for (var i = 0; i < wallConfig.canvas.monitors.length; i++) {
    if (wallConfig.canvas.monitors[i].id === id) return wallConfig.canvas.monitors[i];
  }
  return null;
}

/* ============================================
   PLAYLIST
   ============================================ */

function renderPlaylist(monitorId) {
  var list = document.getElementById('playlistItems');
  list.innerHTML = '';

  var playlist = (wallConfig.playlists || {})[monitorId] || [];

  if (!playlist.length) {
    list.innerHTML = '<li class="empty-hint">Playlist leer \u2014 Assets aus dem Pool rechts hierher ziehen</li>';
    return;
  }

  playlist.forEach(function (item, idx) {
    var li = document.createElement('li');
    li.className = 'pl-item';
    li.draggable = true;
    li.dataset.idx = idx;

    // Aktuell spielendes Asset hervorheben
    var currentIdx = playbackState[monitorId];
    if (typeof currentIdx === 'number' && currentIdx === idx) {
      li.classList.add('pl-now-playing');
    }

    var numSpan = document.createElement('span');
    numSpan.className = 'pl-num';
    if (typeof currentIdx === 'number' && currentIdx === idx) {
      numSpan.innerHTML = '&#9654;';
    } else {
      numSpan.textContent = (idx + 1) + '.';
    }

    var nameSpan = document.createElement('span');
    nameSpan.className = 'pl-name';
    nameSpan.textContent = item.asset;

    // Preview bei Mouseover
    if (item.uri) {
      var mimeGuess = guessType(item.uri);
      if (mimeGuess) {
        (function (uri, type) {
          li.addEventListener('mouseenter', function (e) {
            showPreviewTooltip(assetUrl(uri), type, e);
          });
          li.addEventListener('mousemove', positionTooltip);
          li.addEventListener('mouseleave', hidePreviewTooltip);
        })(item.uri, mimeGuess);
      }
    }

    var durInput = document.createElement('input');
    durInput.type = 'number';
    durInput.className = 'pl-dur-input';
    durInput.value = item.duration || 10;
    durInput.min = 1;
    durInput.max = 9999;
    durInput.title = 'Anzeigedauer in Sekunden';
    durInput.addEventListener('change', function () {
      item.duration = parseInt(durInput.value, 10) || 10;
      wallConfig.playlists[monitorId] = playlist;
      savePlaylist(monitorId);
      showOutput('Dauer: ' + item.asset + ' → ' + item.duration + 's');
    });

    var durLabel = document.createElement('span');
    durLabel.className = 'pl-dur-label';
    durLabel.textContent = 's';

    li.appendChild(numSpan);
    li.appendChild(nameSpan);
    li.appendChild(durInput);
    li.appendChild(durLabel);

    var removeBtn = document.createElement('button');
    removeBtn.className = 'pl-remove';
    removeBtn.textContent = '\u00d7';
    removeBtn.addEventListener('click', function () {
      playlist.splice(idx, 1);
      wallConfig.playlists[monitorId] = playlist;
      savePlaylist(monitorId);
      renderPlaylist(monitorId);
      renderCanvas();
    });
    li.appendChild(removeBtn);

    // Sortierung per Drag
    li.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/plain', JSON.stringify({ type: 'reorder', fromIdx: idx }));
    });

    li.addEventListener('dragover', function (e) {
      e.preventDefault();
      li.classList.add('drag-over');
    });

    li.addEventListener('dragleave', function () {
      li.classList.remove('drag-over');
    });

    li.addEventListener('drop', function (e) {
      e.preventDefault();
      li.classList.remove('drag-over');
      handleDrop(e, monitorId, idx);
    });

    list.appendChild(li);
  });
}

function handleDrop(e, monitorId, targetIdx) {
  var raw = e.dataTransfer.getData('text/plain');
  try { var data = JSON.parse(raw); } catch (_) { return; }

  var playlist = (wallConfig.playlists || {})[monitorId] || [];

  if (data.type === 'reorder') {
    var item = playlist.splice(data.fromIdx, 1)[0];
    playlist.splice(targetIdx, 0, item);
  } else if (data.type === 'pool') {
    playlist.splice(targetIdx + 1, 0, {
      asset: data.name,
      duration: parseInt(data.duration, 10) || 10,
      uri: data.uri,
    });
    showOutput('Asset hinzugefuegt: ' + data.name + ' \u2192 ' + monitorId);
  }

  wallConfig.playlists[monitorId] = playlist;
  savePlaylist(monitorId);
  renderPlaylist(monitorId);
  renderCanvas();
}

/* Drop-Zone (Playlist-Ende) */
(function () {
  var zone = document.getElementById('playlistDropZone');

  zone.addEventListener('dragover', function (e) {
    e.preventDefault();
    zone.classList.add('drop-hover');
  });

  zone.addEventListener('dragleave', function () {
    zone.classList.remove('drop-hover');
  });

  zone.addEventListener('drop', function (e) {
    e.preventDefault();
    zone.classList.remove('drop-hover');
    if (!selectedMonitor || !wallConfig) {
      showOutput('Erst einen Monitor auswaehlen!');
      return;
    }

    var raw = e.dataTransfer.getData('text/plain');
    try { var data = JSON.parse(raw); } catch (_) { return; }
    if (data.type !== 'pool') return;

    if (!wallConfig.playlists) wallConfig.playlists = {};
    if (!wallConfig.playlists[selectedMonitor]) wallConfig.playlists[selectedMonitor] = [];

    wallConfig.playlists[selectedMonitor].push({
      asset: data.name,
      duration: parseInt(data.duration, 10) || 10,
      uri: data.uri,
    });

    savePlaylist(selectedMonitor);
    renderPlaylist(selectedMonitor);
    renderCanvas();
    showOutput('Asset hinzugefuegt: ' + data.name + ' \u2192 ' + selectedMonitor);
  });
})();

/* ============================================
   DISPLAY SETTINGS
   ============================================ */

function renderDisplaySettings() {
  var grid = document.getElementById('displayGrid');
  grid.innerHTML = '';
  if (!wallConfig) return;

  // Monitore nach Pi gruppieren: head, slave1, slave2
  var pis = [
    { name: 'Head-Pi', prefix: 'head', monitors: [] },
    { name: 'Slave 1', prefix: 'slave1', monitors: [] },
    { name: 'Slave 2', prefix: 'slave2', monitors: [] },
  ];

  wallConfig.canvas.monitors.forEach(function (mon) {
    for (var i = 0; i < pis.length; i++) {
      if (mon.id.startsWith(pis[i].prefix)) {
        pis[i].monitors.push(mon);
        break;
      }
    }
  });

  pis.forEach(function (pi) {
    if (!pi.monitors.length) return;

    var card = document.createElement('div');
    card.className = 'pi-card';

    var header = '<div class="pi-card-header"><h3>' + pi.name + '</h3></div>';
    var displays = '';

    pi.monitors.forEach(function (mon) {
      var color = MONITOR_COLORS[mon.id] || '#972c2b';
      var pl = (wallConfig.playlists || {})[mon.id] || [];
      displays +=
        '<div class="pi-display" style="border-left-color:' + color + '">' +
          '<div class="pi-display-name">' + escHtml(mon.label || mon.id) +
            '<span class="pi-display-assets">' + pl.length + ' Assets</span></div>' +
          '<div class="field"><label>Output</label><span>' + mon.output + '</span></div>' +
          '<div class="field"><label>Rotation</label>' +
            '<select data-mon="' + mon.id + '" onchange="setRotation(this)">' +
              '<option value="0"' + (mon.rotation === 0 ? ' selected' : '') + '>0\u00b0 Landscape</option>' +
              '<option value="90"' + (mon.rotation === 90 ? ' selected' : '') + '>90\u00b0 Portrait</option>' +
              '<option value="180"' + (mon.rotation === 180 ? ' selected' : '') + '>180\u00b0</option>' +
              '<option value="270"' + (mon.rotation === 270 ? ' selected' : '') + '>270\u00b0 Portrait</option>' +
            '</select></div>' +
          '<div class="field"><label>Aufloesung</label><span>' + mon.width + '\u00d7' + mon.height + '</span></div>' +
        '</div>';
    });

    card.innerHTML = header + '<div class="pi-displays">' + displays + '</div>';
    grid.appendChild(card);
  });
}

function setRotation(sel) {
  var monId = sel.dataset.mon;
  var rotation = parseInt(sel.value, 10);
  var mon = findMonitor(monId);
  if (!mon) return;
  mon.rotation = rotation;
  saveWallConfig();
  renderCanvas();
  showOutput('Rotation: ' + monId + ' \u2192 ' + rotation + '\u00b0');
}

/* ============================================
   SYNC (Platzhalter fuer WP3)
   ============================================ */

function renderSyncOffsets() {
  var cont = document.getElementById('syncOffsets');
  cont.innerHTML = '';
  if (!wallConfig || !wallConfig.sync) return;

  var offsets = wallConfig.sync.offsets || {};
  Object.keys(offsets).forEach(function (id) {
    var card = document.createElement('div');
    card.className = 'offset-card';
    card.innerHTML =
      '<label>' + id + '</label>' +
      '<input type="number" step="0.1" value="' + offsets[id] + '" ' +
        'data-output="' + id + '" onchange="setSyncOffset(this)">';
    cont.appendChild(card);
  });
}

function setSyncOffset(input) {
  var id = input.dataset.output;
  wallConfig.sync.offsets[id] = parseFloat(input.value) || 0;
  saveWallConfig();
  showOutput('Offset: ' + id + ' \u2192 ' + input.value + 's');
}

function toggleSync() { showOutput('Sync: WP3 — noch nicht implementiert'); }
function syncAll(cmd) { showOutput('Sync ' + cmd + ': WP3 — noch nicht implementiert'); }

/* ============================================
   TOOLBAR COMMANDS
   ============================================ */

var transportState = 'stop';

function cmdAll(cmd) {
  if (cmd === 'play' || cmd === 'pause' || cmd === 'stop') {
    transportState = cmd;
  }
  updateTransportButtons();
  showOutput('Befehl: ' + cmd + ' — wird an alle Viewer gesendet (WP3)');
  // TODO WP3: UDP broadcast an alle Viewer
}

function updateTransportButtons() {
  var play = document.querySelector('.tb-play');
  var pause = document.querySelector('.tb-pause');
  var stop = document.querySelector('.tb-stop');

  if (play) play.classList.toggle('tb-active-play', transportState === 'play');
  if (pause) pause.classList.toggle('tb-active-pause', transportState === 'pause');
  if (stop) stop.classList.toggle('tb-active-stop', transportState === 'stop');
}

function updateToolbarStatus(status) {
  var d1 = document.getElementById('tbDot1');
  var d2 = document.getElementById('tbDot2');
  var temp = document.getElementById('tbTemp');
  if (d1) d1.className = 'tb-dot ' + (status.viewer1_running ? 'green' : 'red');
  if (d2) d2.className = 'tb-dot ' + (status.viewer2_running ? 'green' : 'red');

  // Transport-State aus Viewer-Status ableiten
  if (status.viewer1_running || status.viewer2_running) {
    if (transportState === 'stop') {
      transportState = 'play';
      updateTransportButtons();
    }
  }
  if (temp) {
    var t = (status.temperature || '').replace('temp=', '').replace("'C", '');
    temp.textContent = t ? t + '\u00b0C' : '';
  }
}

/* ============================================
   STATUS
   ============================================ */

function renderStatus(status) {
  var grid = document.getElementById('statusGrid');
  grid.innerHTML = '';

  // Temperatur als Zahl
  var tempStr = (status.temperature || '').replace("temp=", "").replace("'C", "");
  var tempNum = parseFloat(tempStr) || 0;
  var tempOk = tempNum < 70;
  var tempWarn = tempNum >= 60 && tempNum < 70;
  var throttleOk = !status.throttle || status.throttle === '0x0';

  // Als Pi-Karte darstellen (aktuell nur Head, spaeter pro Pi)
  var card = document.createElement('div');
  card.className = 'pi-card';

  var tempDot = tempWarn ? 'yellow' : (tempOk ? 'green' : 'red');
  var thrDot = throttleOk ? 'green' : 'red';

  card.innerHTML =
    '<div class="pi-card-header">' +
      '<h3>' + (status.hostname || 'Pi') + '</h3>' +
      '<span class="pi-card-ip">' + (status.ip || '') + '</span>' +
    '</div>' +
    '<div class="pi-status-grid">' +
      '<div class="pi-stat"><span class="status-dot ' + tempDot + '"></span>Temp<span class="pi-stat-val">' + tempStr + '\u00b0C</span></div>' +
      '<div class="pi-stat"><span class="status-dot ' + thrDot + '"></span>Throttle<span class="pi-stat-val">' + (throttleOk ? 'OK' : status.throttle) + '</span></div>' +
      '<div class="pi-stat"><span class="status-dot green"></span>Uptime<span class="pi-stat-val">' + (status.uptime || 'N/A') + '</span></div>' +
      '<div class="pi-stat"><span class="status-dot green"></span>Disk<span class="pi-stat-val">' + (status.disk || 'N/A') + '</span></div>' +
      '<div class="pi-stat"><span class="status-dot green"></span>RAM<span class="pi-stat-val">' + (status.memory || 'N/A') + '</span></div>' +
    '</div>' +
    '<div class="pi-displays">' +
      '<div class="pi-display" style="border-left-color:#e94560">' +
        '<div class="pi-display-name">HDMI-1 (Viewer 1)' +
          '<span class="status-dot ' + (status.viewer1_running ? 'green' : 'red') + '" style="margin-left:0.5rem"></span>' +
        '</div>' +
      '</div>' +
      '<div class="pi-display" style="border-left-color:#ff6b6b">' +
        '<div class="pi-display-name">HDMI-2 (Viewer 2)' +
          '<span class="status-dot ' + (status.viewer2_running ? 'green' : 'red') + '" style="margin-left:0.5rem"></span>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="pi-meta">' +
      '<div>MAC WLAN: ' + (status.mac_wlan || 'N/A') + '</div>' +
      '<div>MAC ETH: ' + (status.mac_eth || 'N/A') + '</div>' +
    '</div>';

  grid.appendChild(card);

  // Platzhalter fuer Slaves
  ['Slave 1', 'Slave 2'].forEach(function (name) {
    var sc = document.createElement('div');
    sc.className = 'pi-card pi-offline';
    sc.innerHTML =
      '<div class="pi-card-header"><h3>' + name + '</h3><span class="pi-card-ip">Nicht verbunden</span></div>' +
      '<div class="empty-hint" style="padding:1rem">Pi noch nicht eingerichtet</div>';
    grid.appendChild(sc);
  });
}

/* ============================================
   INIT
   ============================================ */

/* ============================================
   FILE UPLOAD
   ============================================ */

function uploadFile(file) {
  var formData = new FormData();
  formData.append('file', file);
  formData.append('filename', file.name);
  formData.append('duration', '10');

  showOutput('Lade hoch: ' + file.name + '...');

  fetch('/api/upload', { method: 'POST', body: formData })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.ok) {
        showOutput('Hochgeladen: ' + file.name);
        loadAssets();
      } else {
        showOutput('Fehler: ' + (data.error || 'Upload fehlgeschlagen'));
      }
    })
    .catch(function (e) {
      showOutput('Upload-Fehler: ' + e.message);
    });
}

// Datei-Input
document.getElementById('fileInput').addEventListener('change', function (e) {
  Array.from(e.target.files).forEach(uploadFile);
  e.target.value = '';
});

// Drag&Drop auf Upload-Zone
(function () {
  var drop = document.getElementById('uploadDrop');
  var sidebar = document.getElementById('poolSidebar');

  // Prevent browser default (open file in tab)
  sidebar.addEventListener('dragover', function (e) {
    // Nur File-Drops abfangen, nicht interne Pool-Drags
    if (e.dataTransfer.types.indexOf('Files') !== -1) {
      e.preventDefault();
      drop.classList.add('drag-over');
    }
  });

  sidebar.addEventListener('dragleave', function (e) {
    if (!sidebar.contains(e.relatedTarget)) {
      drop.classList.remove('drag-over');
    }
  });

  sidebar.addEventListener('drop', function (e) {
    drop.classList.remove('drag-over');
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      e.preventDefault();
      Array.from(e.dataTransfer.files).forEach(uploadFile);
    }
  });
})();

/* ============================================
   INIT
   ============================================ */

/* ============================================
   ASSET HELPERS
   ============================================ */

function guessType(uri) {
  if (!uri) return null;
  var lower = uri.toLowerCase();
  if (/\.(jpe?g|png|gif|bmp|webp|svg)/.test(lower)) return 'image';
  if (/\.(mp4|webm|mov|avi|mkv)/.test(lower)) return 'video';
  return null;
}

function assetUrl(uri) {
  // Absolute Pfade (z.B. /home/head/screenly_assets/UUID.jpg) in Browser-URL umwandeln
  if (!uri) return uri;
  var match = uri.match(/screenly_assets\/(.+)$/);
  if (match) return '/assets/' + match[1];
  // Docker-Pfade
  var match2 = uri.match(/\/data\/screenly_assets\/(.+)$/);
  if (match2) return '/assets/' + match2[1];
  return uri;
}

/* ============================================
   PREVIEW TOOLTIP
   ============================================ */

var previewEl = null;

function showPreviewTooltip(uri, type, event) {
  hidePreviewTooltip();
  if (!uri) return;

  previewEl = document.createElement('div');
  previewEl.className = 'preview-tooltip';

  if (type === 'image') {
    var img = document.createElement('img');
    img.src = uri;
    img.alt = 'Preview';
    previewEl.appendChild(img);
  } else if (type === 'video') {
    var vid = document.createElement('video');
    vid.src = uri;
    vid.muted = true;
    vid.autoplay = true;
    vid.loop = true;
    vid.playsInline = true;
    previewEl.appendChild(vid);
  }

  document.body.appendChild(previewEl);
  positionTooltip(event);
}

function positionTooltip(e) {
  if (!previewEl) return;
  var x = e.clientX - 220;
  var y = e.clientY - 10;
  if (x < 10) x = e.clientX + 20;
  if (y < 10) y = 10;
  previewEl.style.left = x + 'px';
  previewEl.style.top = y + 'px';
}

function hidePreviewTooltip() {
  if (previewEl) {
    // Video stoppen
    var vid = previewEl.querySelector('video');
    if (vid) { vid.pause(); vid.src = ''; }
    previewEl.remove();
    previewEl = null;
  }
}

/* ============================================
   PLAYBACK STATUS (aktuelle Position)
   ============================================ */

var playbackState = {};

async function loadPlaybackState() {
  try {
    var res = await fetch('/api/playback');
    var newState = await res.json();
    // Nur neu rendern wenn sich etwas geaendert hat
    var changed = false;
    for (var key in newState) {
      if (playbackState[key] !== newState[key]) { changed = true; break; }
    }
    playbackState = newState;
    if (changed && selectedMonitor) renderPlaylist(selectedMonitor);
  } catch (e) { /* API existiert eventuell noch nicht */ }
}

/* ============================================
   INIT
   ============================================ */

loadAssets();
loadWallConfig();
loadStatus();
loadPlaybackState();
setInterval(loadStatus, 5000);
setInterval(loadAssets, 15000);
setInterval(loadPlaybackState, 3000);
