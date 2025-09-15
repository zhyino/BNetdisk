const rootsEl = document.getElementById('roots');
const entriesEl = document.getElementById('entries');
const cwdPathEl = document.getElementById('cwdPath');
const srcListEl = document.getElementById('srcList');
const dstListEl = document.getElementById('dstList');
const queueEl = document.getElementById('queue');
const logEl = document.getElementById('log');
const addPairsBtn = document.getElementById('addPairs');
const clearBtn = document.getElementById('clearSelected');

let currentPath = null;
let srcs = [];
let dsts = [];

async function loadRoots() {
  const res = await fetch('/api/listdir');
  const data = await res.json();
  const roots = data.roots || [];
  rootsEl.innerHTML = '';
  roots.forEach(r => {
    const btn = document.createElement('button');
    btn.className = 'root-btn';
    btn.innerText = r;
    btn.onclick = () => { browse(r); };
    rootsEl.appendChild(btn);
  });
  if (roots.length) browse(roots[0]);
}

async function browse(path) {
  currentPath = path;
  cwdPathEl.innerText = path;
  entriesEl.innerHTML = '<div class="loading">Loading...</div>';
  const res = await fetch('/api/listdir?path=' + encodeURIComponent(path));
  const data = await res.json();
  if (data.error) {
    entriesEl.innerText = data.error;
    return;
  }
  entriesEl.innerHTML = '';
  const up = document.createElement('div');
  up.className = 'entry up';
  up.innerText = '.. (up)'
  up.onclick = () => {
    const parent = path.split('/').slice(0, -1).join('/') || '/';
    browse(parent);
  }
  entriesEl.appendChild(up);
  data.entries.forEach(e => {
    const el = document.createElement('div');
    el.className = 'entry ' + (e.is_dir ? 'dir' : 'file');
    el.innerText = e.name;
    el.onclick = () => {
      if (e.is_dir) browse(e.path);
    };
    const addSrc = document.createElement('button');
    addSrc.innerText = '+Src';
    addSrc.onclick = (ev) => { ev.stopPropagation(); addToList('src', e.path); };
    const addDst = document.createElement('button');
    addDst.innerText = '+Dst';
    addDst.onclick = (ev) => { ev.stopPropagation(); addToList('dst', e.path); };
    el.appendChild(addSrc);
    el.appendChild(addDst);
    entriesEl.appendChild(el);
  });
}

function addToList(type, p) {
  if (type === 'src') {
    if (!srcs.includes(p)) srcs.push(p);
    renderLists();
  } else {
    if (!dsts.includes(p)) dsts.push(p);
    renderLists();
  }
}

function renderLists() {
  srcListEl.innerHTML = '';
  srcs.forEach((s, i) => {
    const li = document.createElement('li');
    li.innerText = s;
    const rem = document.createElement('button');
    rem.innerText = 'x';
    rem.onclick = () => { srcs.splice(i,1); renderLists(); };
    li.appendChild(rem);
    srcListEl.appendChild(li);
  });
  dstListEl.innerHTML = '';
  dsts.forEach((d, i) => {
    const li = document.createElement('li');
    li.innerText = d;
    const rem = document.createElement('button');
    rem.innerText = 'x';
    rem.onclick = () => { dsts.splice(i,1); renderLists(); };
    li.appendChild(rem);
    dstListEl.appendChild(li);
  });
}

addPairsBtn.onclick = async () => {
  const n = Math.min(srcs.length, dsts.length);
  if (n === 0) { alert('需要至少一对 src/dst'); return; }
  const tasks = [];
  for (let i=0;i<n;i++) {
    tasks.push({ src: srcs[i], dst: dsts[i] });
  }
  const res = await fetch('/api/add', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ tasks, filter_images: true, filter_nfo: false })
  });
  const j = await res.json();
  if (res.ok) {
    srcs = srcs.slice(n);
    dsts = dsts.slice(n);
    renderLists();
    loadQueue();
  } else {
    alert('添加失败: ' + JSON.stringify(j));
  }
};

clearBtn.onclick = () => { srcs = []; dsts = []; renderLists(); };

async function loadQueue() {
  const res = await fetch('/api/queue');
  const j = await res.json();
  queueEl.innerHTML = '';
  j.queue.forEach((it, idx) => {
    const li = document.createElement('li');
    li.innerText = `${it.src} → ${it.dst}`;
    queueEl.appendChild(li);
  });
}

function initLogStream() {
  const es = new EventSource('/stream');
  es.onmessage = (e) => {
    logEl.textContent += e.data + '\n';
    logEl.scrollTop = logEl.scrollHeight;
  };
}

window.onload = () => {
  loadRoots();
  initLogStream();
  loadQueue();
};
