const srcRootSelect = document.getElementById('srcRootSelect');
const srcSubSelect = document.getElementById('srcSubSelect');
const dstRootSelect = document.getElementById('dstRootSelect');
const dstSubSelect = document.getElementById('dstSubSelect');
const chooseSrcBtn = document.getElementById('chooseSrcBtn');
const chooseDstBtn = document.getElementById('chooseDstBtn');
const srcListEl = document.getElementById('srcList');
const dstListEl = document.getElementById('dstList');
const addPairsBtn = document.getElementById('addPairs');
const clearBtn = document.getElementById('clearSelected');
const pairModeEl = document.getElementById('pairMode');
const queueEl = document.getElementById('queue');
const logEl = document.getElementById('log');

let srcs = [];
let dsts = [];

async function loadRootsToSelects() {
  const res = await fetch('/api/roots');
  const data = await res.json();
  const roots = data.roots || [];
  populateRootSelect(srcRootSelect, roots);
  populateRootSelect(dstRootSelect, roots);
  if (roots.length) {
    onRootChange(srcRootSelect, srcSubSelect);
    onRootChange(dstRootSelect, dstSubSelect);
  }
}

function populateRootSelect(selectEl, roots) {
  selectEl.innerHTML = '';
  roots.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r;
    opt.innerText = r;
    selectEl.appendChild(opt);
  });
}

async function onRootChange(rootSelect, subSelect) {
  const root = rootSelect.value;
  subSelect.innerHTML = '';
  const optRoot = document.createElement('option');
  optRoot.value = root;
  optRoot.innerText = root + ' (根目录)';
  subSelect.appendChild(optRoot);

  try {
    const res = await fetch('/api/listdir?path=' + encodeURIComponent(root));
    const j = await res.json();
    if (j.entries) {
      j.entries.forEach(e => {
        if (e.is_dir) {
          const o = document.createElement('option');
          o.value = e.path;
          o.innerText = e.name;
          subSelect.appendChild(o);
        }
      });
    }
  } catch (err) {
    // ignore fetch errors
  }
}

srcRootSelect.onchange = () => onRootChange(srcRootSelect, srcSubSelect);
dstRootSelect.onchange = () => onRootChange(dstRootSelect, dstSubSelect);

// Add to selected lists. keep lists unique for UI clarity
chooseSrcBtn.onclick = () => {
  const v = srcSubSelect.value || srcRootSelect.value;
  if (v && !srcs.includes(v)) srcs.push(v);
  renderLists();
};
chooseDstBtn.onclick = () => {
  const v = dstSubSelect.value || dstRootSelect.value;
  if (v && !dsts.includes(v)) dsts.push(v);
  renderLists();
};

function renderLists() {
  // render pills/cards for selected items with clear buttons
  srcListEl.innerHTML = '';
  srcs.forEach((s, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    pill.innerHTML = `<div class="pname">${s}</div><div class="pactions"><button class="small" onclick="removeSrc(${i})">移除</button></div>`;
    srcListEl.appendChild(pill);
  });
  dstListEl.innerHTML = '';
  dsts.forEach((d, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    pill.innerHTML = `<div class="pname">${d}</div><div class="pactions"><button class="small" onclick="removeDst(${i})">移除</button></div>`;
    dstListEl.appendChild(pill);
  });
}

window.removeSrc = (i) => { srcs.splice(i,1); renderLists(); };
window.removeDst = (i) => { dsts.splice(i,1); renderLists(); };

addPairsBtn.onclick = async () => {
  const mode = pairModeEl.value;
  let tasks = [];
  if (mode === 'index') {
    const n = Math.min(srcs.length, dsts.length);
    if (n === 0) { alert('至少需要一对源和目标'); return; }
    for (let i=0;i<n;i++) {
      if (srcs[i] === dsts[i]) {
        // client-side warn and skip identical pairs
        alert('警告：源和目标相同，已跳过: ' + srcs[i]);
        continue;
      }
      tasks.push({src: srcs[i], dst: dsts[i]});
    }
  } else {
    if (dsts.length === 0) { alert('请先选择一个目标'); return; }
    const target = dsts[0];
    for (let i=0;i<srcs.length;i++) {
      if (srcs[i] === target) {
        // skip identical
        continue;
      }
      tasks.push({src: srcs[i], dst: target});
    }
  }

  if (tasks.length === 0) { alert('没有可添加的任务（可能因为源与目标相同或未选择）'); return; }

  const res = await fetch('/api/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({tasks})
  });
  const j = await res.json();
  if (res.ok) {
    // UX: clear used sources in 'single' mode, in index mode remove matched pairs
    if (mode === 'index') {
      const n = Math.min(srcs.length, dsts.length);
      srcs = srcs.slice(n);
      dsts = dsts.slice(n);
    } else {
      srcs = [];
    }
    renderLists();
    loadQueue();
    if (j.skipped && j.skipped.length) {
      alert('部分任务在服务器端被跳过，原因见日志或返回信息');
    }
  } else {
    alert('添加失败: ' + JSON.stringify(j));
  }
};

clearBtn.onclick = () => { srcs = []; dsts = []; renderLists(); };

async function loadQueue() {
  const res = await fetch('/api/queue');
  const j = await res.json();
  queueEl.innerHTML = '';
  j.queue.forEach((it) => {
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
  loadRootsToSelects();
  initLogStream();
  loadQueue();
};
