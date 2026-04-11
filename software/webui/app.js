/* Displaywall Manager — Frontend-Logik */

const PREFIX = '2:';
let assets = [];
let displays = {};

async function loadData() {
  try {
    const [aRes, dRes, sRes] = await Promise.all([
      fetch('/api/assets'),
      fetch('/api/displays'),
      fetch('/api/status'),
    ]);
    assets = await aRes.json();
    displays = await dRes.json();
    const status = await sRes.json();
    render(status);
  } catch (e) {
    console.error('Fehler beim Laden:', e);
  }
}

function escHtml(s) {
  const d = document.createElement('div');
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

function renderAssetList(el, items, targetDisplay) {
  el.innerHTML = '';

  if (!items.length) {
    el.innerHTML = '<li class="empty-msg">Keine Assets zugewiesen</li>';
    return;
  }

  items.forEach(function (a) {
    const displayName = a.name.startsWith(PREFIX)
      ? a.name.slice(PREFIX.length)
      : a.name;
    const btnLabel = targetDisplay === 2 ? '\u2192 Display 2' : '\u2190 Display 1';
    const enabled = a.is_enabled ? '' : ' (deaktiviert)';

    const li = document.createElement('li');
    li.className = 'asset-item';
    li.innerHTML =
      '<div class="asset-info">' +
        '<div class="asset-name">' + escHtml(displayName) + enabled +
          '<span class="asset-badge ' + badgeClass(a.mimetype) + '">' +
            badgeLabel(a.mimetype) +
          '</span>' +
        '</div>' +
        '<div class="asset-meta">' + a.duration + 's &middot; Order: ' + a.play_order + '</div>' +
      '</div>';

    const btn = document.createElement('button');
    btn.className = 'btn-move';
    btn.textContent = btnLabel;
    btn.addEventListener('click', function () { moveAsset(a.asset_id, targetDisplay); });
    li.appendChild(btn);
    el.appendChild(li);
  });
}

function render(status) {
  var d1 = [], d2 = [];
  assets.forEach(function (a) {
    if (a.name.startsWith(PREFIX)) d2.push(a);
    else d1.push(a);
  });

  renderAssetList(document.getElementById('list1'), d1, 2);
  renderAssetList(document.getElementById('list2'), d2, 1);

  // Rotation-Dropdowns aktualisieren
  document.querySelectorAll('.rotation-select').forEach(function (sel) {
    var output = sel.dataset.output;
    var rot = (displays[output] || {}).rotation || 0;
    sel.value = rot;
  });

  // Status-Dots
  document.getElementById('dotViewer1').className =
    'dot ' + (status.viewer1_running ? 'green' : 'red');
  document.getElementById('dotViewer2').className =
    'dot ' + (status.viewer2_running ? 'green' : 'red');
  document.getElementById('tempItem').textContent = status.temperature || '';

  // Asset-Zaehler
  document.getElementById('info1').textContent =
    d1.filter(function (a) { return a.is_enabled; }).length + ' aktive Assets';
  document.getElementById('info2').textContent =
    d2.filter(function (a) { return a.is_enabled; }).length + ' aktive Assets';
}

async function moveAsset(id, target) {
  await fetch('/api/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_id: id, target: target }),
  });
  loadData();
}

async function setRotation(sel) {
  var output = sel.dataset.output;
  var rotation = parseInt(sel.value, 10);
  await fetch('/api/rotation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ output: output, rotation: rotation }),
  });
  document.getElementById('rebootHint').style.display = 'block';
  loadData();
}

// Init
loadData();
setInterval(loadData, 5000);
