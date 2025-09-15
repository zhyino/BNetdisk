\
/* front-end JS (polling-only for logs, keeps only latest 200 logs shown) */
const srcRootSelect = document.getElementById('srcRootSelect');
const dstRootSelect = document.getElementById('dstRootSelect');
const srcEntries = document.getElementById('srcEntries');
const dstEntries = document.getElementById('dstEntries');
const srcBreadcrumb = document.getElementById('srcBreadcrumb');
const dstBreadcrumb = document.getElementById('dstBreadcrumb');
const srcUpBtn = document.getElementById('srcUpBtn');
const dstUpBtn = document.getElementById('dstUpBtn');
const refreshRootsBtn = document.getElementById('refreshRoots');

const chooseSrcBtn = document.getElementById('chooseSrcBtn');
const chooseDstBtn = document.getElementById('chooseDstBtn');
const srcListEl = document.getElementById('srcList');
const dstListEl = document.getElementById('dstList');
const addPairsBtn = document.getElementById('addPairs');
const clearBtn = document.getElementById('clearSelected');
const queueEl = document.getElementById('queue');
const logEl = document.getElementById('log');

let srcs = []; // {path, root}
let dsts = []; // {path, root}

let currentSrcPath = null;
let currentDstPath = null;

let loadingRoots = false;
let loadingSrc = false;
let loadingDst = false;

const DEFAULT_FETCH_TIMEOUT = 8000;
let pollInterval = null;

function fetchWithTimeout(url, opts = {}, timeout = DEFAULT_FETCH_TIMEOUT) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  return fetch(url, Object.assign({}, opts, {signal: controller.signal})).finally(() => clearTimeout(id));
}

async function loadRootsToSelects() {
  if (loadingRoots) return;
  loadingRoots = true;
  refreshRootsBtn.disabled = true;
  refreshRootsBtn.textContent = '刷新中...';
  try {
    srcRootSelect.innerHTML = '<option>加载中...</option>';
    dstRootSelect.innerHTML = '<option>加载中...</option>';
    const res = await fetchWithTimeout('/api/roots');
    if (!res.ok) throw new Error('加载挂载点失败');
    const data = await res.json();
    const roots = data.roots || [];
    populateRootSelect(srcRootSelect, roots);
    populateRootSelect(dstRootSelect, roots);
    if (roots.length) {
      currentSrcPath = roots[0];
      currentDstPath = roots[0];
      await Promise.all([loadEntries(currentSrcPath, 'src'), loadEntries(currentDstPath, 'dst')]);
    } else {
      srcEntries.innerHTML = '<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
      dstEntries.innerHTML = '<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
    }
  } catch (err) {
    srcRootSelect.innerHTML = '<option>加载失败</option>';
    dstRootSelect.innerHTML = '<option>加载失败</option>';
    srcEntries.innerHTML = '<div class="err">加载挂载点失败，请点击右上“刷新挂载点”或检查容器 volumes。</div>';
    dstEntries.innerHTML = '<div class="err">加载挂载点失败，请点击右上“刷新挂载点”或检查容器 volumes。</div>';
    console.error('loadRootsToSelects error', err);
  } finally {
    loadingRoots = false;
    refreshRootsBtn.disabled = false;
    refreshRootsBtn.textContent = '刷新挂载点';
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
  if (which === 'src' && loadingSrc) return;
  if (which === 'dst' && loadingDst) return;
  if (which === 'src') loadingSrc = true; else loadingDst = true;
  const container = which === 'src' ? srcEntries : dstEntries;
  const breadcrumb = which === 'src' ? srcBreadcrumb : dstBreadcrumb;
  container.innerHTML = '加载中...';
  try {
    const res = await fetchWithTimeout('/api/listdir?path=' + encodeURIComponent(path));
    if (!res.ok) {
      const txt = await res.text();
      container.innerHTML = '<div class="err">读取目录失败: ' + (txt || res.statusText) + '</div>';
      return;
    }
    const j = await res.json();
    if (j.error) {
      container.innerHTML = '<div class="err">' + j.error + '</div>';
      return;
    }
    const entries = j.entries || [];
    container.innerHTML = '';
    breadcrumb.innerHTML = '';
    const rootBtn = document.createElement('button');
    rootBtn.className = 'crumb';
    rootBtn.innerText = path;
    rootBtn.onclick = async () => {
      if (which === 'src') { currentSrcPath = path; await loadEntries(currentSrcPath, 'src'); }
      else { currentDstPath = path; await loadEntries(currentDstPath, 'dst'); }
    };
    breadcrumb.appendChild(rootBtn);
    for (const e of entries) {
      const div = document.createElement('div');
      div.className = 'entry' + (e.is_dir ? ' dir' : ' file');
      const nameEl = document.createElement('div');
      nameEl.innerText = e.name + (e.is_dir ? '/' : '');
      const actionEl = document.createElement('div');
      if (e.is_dir) {
        div.onclick = async (ev) => {
          if (ev.target !== div && ev.target !== nameEl) return;
          if (which === 'src') {
            currentSrcPath = e.path;
            await loadEntries(currentSrcPath, 'src');
          } else {
            currentDstPath = e.path;
            await loadEntries(currentDstPath, 'dst');
          }
        };
      }
      div.appendChild(nameEl);
      div.appendChild(actionEl);
      container.appendChild(div);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      container.innerHTML = '<div class="err">请求超时（目录读取可能较大或挂载点不可用），请重试或刷新挂载点。</div>';
    } else {
      container.innerHTML = '<div class="err">加载失败: ' + (err.message || err) + '</div>';
    }
    console.error('loadEntries error', err);
  } finally {
    if (which === 'src') loadingSrc = false; else loadingDst = false;
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
  const root = srcRootSelect.value || '/';
  if (v) srcs.push({path: v, root: root});
  renderLists();
};
chooseDstBtn.onclick = () => {
  const v = currentDstPath;
  const root = dstRootSelect.value || '/';
  if (v) dsts.push({path: v, root: root});
  renderLists();
};

function renderLists() {
  srcListEl.innerHTML = '';
  srcs.forEach((s, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    const disp = s.path + '  (' + s.root + ')';
    pill.innerHTML = `<div class="pname">${i+1}. ${disp}</div><div class="pactions"><button class="small" onclick="removeSrc(${i})">移除</button></div>`;
    srcListEl.appendChild(pill);
  });
  dstListEl.innerHTML = '';
  dsts.forEach((d, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    const disp = d.path + '  (' + d.root + ')';
    pill.innerHTML = `<div class="pname">${i+1}. ${disp}</div><div class="pactions"><button class="small" onclick="removeDst(${i})">移除</button></div>`;
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
    const s = srcs[i];
    const d = dsts[i];
    if (!s || !d) continue;
    if (s.path === d.path) {
      alert('警告：源和目标相同，已跳过: ' + s.path);
      continue;
    }
    tasks.push({src: s.path, src_root: s.root, dst: d.path, dst_root: d.root, mode: mode});
  }
  if (tasks.length === 0) { alert('没有可添加的任务（可能因为源与目标相同）'); return; }
  try {
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
  } catch (err) {
    alert('添加任务失败，请检查网络或服务端: ' + err.message);
  }
};

clearBtn.onclick = () => { srcs = []; dsts = []; renderLists(); };

async function loadQueue() {
  try {
    const res = await fetch('/api/queue');
    const j = await res.json();
    queueEl.innerHTML = '';
    j.queue.forEach((it, idx) => {
      const li = document.createElement('li');
      li.innerText = `${idx+1}. ${it.src} → ${it.dst} (mode=${it.mode||'incremental'})`;
      queueEl.appendChild(li);
    });
  } catch (err) {
    queueEl.innerHTML = '<li class="err">无法加载队列</li>';
  }
}

// polling-only log handling
async function fetchLogsOnce() {
  try {
    const res = await fetch('/api/logs?n=200');
    if (!res.ok) return;
    const j = await res.json();
    const lines = j.lines || [];
    logEl.textContent = lines.join('\\n') + (lines.length ? '\\n' : '');
    logEl.scrollTop = logEl.scrollHeight;
  } catch (err) {
    console.warn('fetchLogsOnce error', err);
  }
}

function startPollingLogs() {
  if (pollInterval) return;
  fetchLogsOnce();
  pollInterval = setInterval(fetchLogsOnce, 3000);
}

refreshRootsBtn.onclick = async () => {
  await loadRootsToSelects();
};

window.onload = () => {
  loadRootsToSelects();
  startPollingLogs();
  loadQueue();
  setInterval(loadQueue, 5000); // keep queue updated
};
