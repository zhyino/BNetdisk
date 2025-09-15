const srcRootSelect = document.getElementById('srcRootSelect');
const dstRootSelect = document.getElementById('dstRootSelect');
const srcEntries = document.getElementById('srcEntries');
const dstEntries = document.getElementById('dstEntries');
const srcBreadcrumb = document.getElementById('srcBreadcrumb');
const dstBreadcrumb = document.getElementById('dstBreadcrumb');
const srcUpBtn = document.getElementById('srcUpBtn');
const dstUpBtn = document.getElementById('dstUpBtn');

const chooseSrcBtn = document.getElementById('chooseSrcBtn');
const chooseDstBtn = document.getElementById('chooseDstBtn');
const srcListEl = document.getElementById('srcList');
const dstListEl = document.getElementById('dstList');
const addPairsBtn = document.getElementById('addPairs');
const clearBtn = document.getElementById('clearSelected');
const queueEl = document.getElementById('queue');
const logEl = document.getElementById('log');

let srcs = [];
let dsts = [];

let currentSrcPath = null;
let currentDstPath = null;

async function loadRootsToSelects() {
  const res = await fetch('/api/roots');
  const data = await res.json();
  const roots = data.roots || [];
  populateRootSelect(srcRootSelect, roots);
  populateRootSelect(dstRootSelect, roots);
  if (roots.length) {
    currentSrcPath = roots[0];
    currentDstPath = roots[0];
    await loadEntries(currentSrcPath, 'src');
    await loadEntries(currentDstPath, 'dst');
  }
}

function populateRootSelect(sel, roots) {
  sel.innerHTML = '';
  roots.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r;
    opt.innerText = r;
    sel.appendChild(opt);
  });
  sel.onchange = async () => {
    const v = sel.value;
    if (sel === srcRootSelect) {
      currentSrcPath = v;
      await loadEntries(currentSrcPath, 'src');
    } else {
      currentDstPath = v;
      await loadEntries(currentDstPath, 'dst');
    }
  };
}

async function loadEntries(path, which) {
  const container = which === 'src' ? srcEntries : dstEntries;
  const breadcrumb = which === 'src' ? srcBreadcrumb : dstBreadcrumb;
  container.innerHTML = '加载中...';
  try {
    const res = await fetch('/api/listdir?path=' + encodeURIComponent(path));
    const j = await res.json();
    if (j.error) {
      container.innerHTML = '<div class="err">' + j.error + '</div>';
      return;
    }
    const entries = j.entries || [];
    container.innerHTML = '';
    breadcrumb.innerHTML = '';
    // root display
    const rootBtn = document.createElement('button');
    rootBtn.className = 'crumb';
    rootBtn.innerText = path;
    rootBtn.onclick = async () => {
      if (which === 'src') { currentSrcPath = path; await loadEntries(currentSrcPath, 'src'); }
      else { currentDstPath = path; await loadEntries(currentDstPath, 'dst'); }
    };
    breadcrumb.appendChild(rootBtn);
    entries.forEach(e => {
      const div = document.createElement('div');
      div.className = 'entry' + (e.is_dir ? ' dir' : ' file');
      div.innerText = e.name + (e.is_dir ? '/' : '');
      if (e.is_dir) {
        div.onclick = async () => {
          if (which === 'src') {
            currentSrcPath = e.path;
            await loadEntries(currentSrcPath, 'src');
          } else {
            currentDstPath = e.path;
            await loadEntries(currentDstPath, 'dst');
          }
        };
      }
      container.appendChild(div);
    });
  } catch (err) {
    container.innerHTML = '<div class="err">加载失败</div>';
  }
}

srcUpBtn.onclick = async () => {
  if (!currentSrcPath) return;
  const p = currentSrcPath;
  const parent = p === '/' ? '/' : p.split('/').slice(0,-1).join('/') || '/';
  currentSrcPath = parent;
  await loadEntries(currentSrcPath, 'src');
};
dstUpBtn.onclick = async () => {
  if (!currentDstPath) return;
  const p = currentDstPath;
  const parent = p === '/' ? '/' : p.split('/').slice(0,-1).join('/') || '/';
  currentDstPath = parent;
  await loadEntries(currentDstPath, 'dst');
};

chooseSrcBtn.onclick = () => {
  const v = currentSrcPath;
  if (v) srcs.push(v); // allow duplicates if user wants
  renderLists();
};
chooseDstBtn.onclick = () => {
  const v = currentDstPath;
  if (v) dsts.push(v);
  renderLists();
};

function renderLists() {
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
  const n = Math.min(srcs.length, dsts.length);
  if (n === 0) { alert('至少需要一对源和目标（按索引配对）'); return; }
  const mode = document.querySelector('input[name="mode"]:checked').value || 'incremental';
  let tasks = [];
  for (let i=0;i<n;i++) {
    if (srcs[i] === dsts[i]) {
      alert('警告：源和目标相同，已跳过: ' + srcs[i]);
      continue;
    }
    tasks.push({src: srcs[i], dst: dsts[i], mode: mode});
  }
  if (tasks.length === 0) { alert('没有可添加的任务（可能因为源与目标相同）'); return; }
  const res = await fetch('/api/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({tasks})
  });
  const j = await res.json();
  if (res.ok) {
    srcs = srcs.slice(n);
    dsts = dsts.slice(n);
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
    li.innerText = `${it.src} → ${it.dst} (mode=${it.mode||'incremental'})`;
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
