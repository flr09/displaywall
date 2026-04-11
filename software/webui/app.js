/* Displaywall VJ-Manager — Frontend-Logik */

let assets = [];
let displays = {};

async function loadData() {
  try {
    const [aRes, sRes] = await Promise.all([
      fetch('/api/assets'),
      fetch('/api/status'),
    ]);
    assets = await aRes.json();
    const status = await sRes.json();
    renderStatus(status);
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

function renderStatus(status) {
  var dot1 = document.getElementById('dotViewer1');
  var dot2 = document.getElementById('dotViewer2');
  var temp = document.getElementById('tempItem');

  if (dot1) {
    dot1.className = 'dot ' + (status.viewer1_running ? 'green' : 'red');
  }
  if (dot2) {
    dot2.className = 'dot ' + (status.viewer2_running ? 'green' : 'red');
  }
  if (temp) {
    temp.textContent = status.temperature || '';
  }
}
