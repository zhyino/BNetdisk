/* front-end JS for BNetdisk panel */
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
const srcCountEl = document.getElementById('srcCount');
const dstCountEl = document.getElementById('dstCount');
const queueCountEl = document.getElementById('queueCount');
const connectionStatus = document.getElementById('connectionStatus');
const connectionText = document.getElementById('connectionText');
const clearLogBtn = document.getElementById('clearLogBtn');
const toastHost = document.getElementById('toastHost');

let srcs = [];
let dsts = [];
let currentSrcPath = null;
let currentDstPath = null;
let currentSrcRoot = null;
let currentDstRoot = null;
let loadingRoots = false;
let loadingSrc = false;
let loadingDst = false;
let es = null;
let pollInterval = null;
let reconnectTimer = null;

const DEFAULT_FETCH_TIMEOUT = 8000;
const MAX_LOG_LINES = 100;

function setConnectionState(state, text) {
  if (!connectionStatus || !connectionText) return;
  connectionStatus.classList.remove('online', 'offline', 'polling');
  if (state) connectionStatus.classList.add(state);
  connectionText.textContent = text;
}

function toast(message, type = 'info', timeout = 3200) {
  if (!toastHost) {
    console.log(message);
    return;
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  toastHost.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    el.style.transition = '0.2s ease';
    setTimeout(() => el.remove(), 220);
  }, timeout);
}

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function fetchWithTimeout(url, opts = {}, timeout = DEFAULT_FETCH_TIMEOUT) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  return fetch(url, Object.assign({}, opts, { signal: controller.signal }))
    .finally(() => clearTimeout(id));
}

function parentPath(path) {
  if (!path || path === '/') return '/';
  const cleaned = path.replace(/\/+$/, '');
  const idx = cleaned.lastIndexOf('/');
  if (idx <= 0) return '/';
  return cleaned.slice(0, idx) || '/';
}

function buildBreadcrumb(path, which) {
  const breadcrumb = which === 'src' ? srcBreadcrumb : dstBreadcrumb;
  const root = which === 'src' ? (currentSrcRoot || path) : (currentDstRoot || path);
  breadcrumb.innerHTML = '';

  const parts = [];
  if (path === root) {
    parts.push({ label: root, value: root });
  } else if (path.startsWith(root + '/') || path === root) {
    parts.push({ label: root, value: root });
    const rest = path.slice(root.length).replace(/^\/+/, '');
    if (rest) {
      const segs = rest.split('/').filter(Boolean);
      let acc = root === '/' ? '' : root;
      for (const seg of segs) {
        acc = (acc === '/' ? '' : acc) + '/' + seg;
        if (acc.startsWith('//')) acc = acc.slice(1);
        parts.push({ label: seg, value: acc });
      }
    }
  } else {
    parts.push({ label: path, value: path });
  }

  parts.forEach((part, index) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'crumb';
    btn.textContent = part.label;
    btn.title = part.value;
    btn.onclick = async () => {
      if (which === 'src') {
        currentSrcPath = part.value;
        await loadEntries(currentSrcPath, 'src');
      } else {
        currentDstPath = part.value;
        await loadEntries(currentDstPath, 'dst');
      }
    };
    breadcrumb.appendChild(btn);
    if (index < parts.length - 1) {
      const sep = document.createElement('span');
      sep.className = 'muted-msg';
      sep.style.padding = '0';
      sep.style.fontSize = '12px';
      sep.textContent = '/';
      breadcrumb.appendChild(sep);
    }
  });
}

async function loadRootsToSelects() {
  if (loadingRoots) return;
  loadingRoots = true;
  refreshRootsBtn.disabled = true;
  const oldText = refreshRootsBtn.textContent;
  refreshRootsBtn.textContent = '刷新中...';
  try {
    srcRootSelect.innerHTML = '<option>加载中...</option>';
    dstRootSelect.innerHTML = '<option>加载中...</option>';
    const res = await fetchWithTimeout('/api/roots');
    if (!res.ok) throw new Error('加载挂载点失败');
    const data = await res.json();
    const roots = data.roots || [];
    populateRootSelect(srcRootSelect, roots, 'src');
    populateRootSelect(dstRootSelect, roots, 'dst');
    if (roots.length) {
      currentSrcRoot = roots[0];
      currentDstRoot = roots[0];
      currentSrcPath = roots[0];
      currentDstPath = roots[0];
      await Promise.all([
        loadEntries(currentSrcPath, 'src'),
        loadEntries(currentDstPath, 'dst'),
      ]);
      toast(`已加载 ${roots.length} 个挂载点`, 'success');
    } else {
      srcEntries.innerHTML = '<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
      dstEntries.innerHTML = '<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
      toast('未发现挂载点', 'warn');
    }
  } catch (err) {
    srcRootSelect.innerHTML = '<option>加载失败</option>';
    dstRootSelect.innerHTML = '<option>加载失败</option>';
    srcEntries.innerHTML = '<div class="err">加载挂载点失败，请点击“刷新挂载点”或检查容器 volumes。</div>';
    dstEntries.innerHTML = '<div class="err">加载挂载点失败，请点击“刷新挂载点”或检查容器 volumes。</div>';
    toast('加载挂载点失败', 'error');
    console.error('loadRootsToSelects error', err);
  } finally {
    loadingRoots = false;
    refreshRootsBtn.disabled = false;
    refreshRootsBtn.textContent = oldText || '刷新挂载点';
  }
}

function populateRootSelect(sel, roots, which) {
  sel.innerHTML = '';
  roots.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = r;
    opt.textContent = r;
    sel.appendChild(opt);
  });
  sel.onchange = async () => {
    const v = sel.value;
    if (which === 'src') {
      currentSrcRoot = v;
      currentSrcPath = v;
      await loadEntries(currentSrcPath, 'src');
    } else {
      currentDstRoot = v;
      currentDstPath = v;
      await loadEntries(currentDstPath, 'dst');
    }
  };
}

async function loadEntries(path, which) {
  if (which === 'src' && loadingSrc) return;
  if (which === 'dst' && loadingDst) return;
  if (which === 'src') loadingSrc = true;
  else loadingDst = true;

  const container = which === 'src' ? srcEntries : dstEntries;
  container.innerHTML = '<div class="muted-msg">加载中...</div>';

  try {
    const res = await fetchWithTimeout('/api/listdir?path=' + encodeURIComponent(path));
    const raw = await res.text();
    let j = {};
    try {
      j = raw ? JSON.parse(raw) : {};
    } catch (_) {
      j = { error: raw || res.statusText || 'invalid response' };
    }
    if (!res.ok) {
      const message = (j && j.error) || raw || res.statusText || '读取失败';
      container.innerHTML = `<div class="err">读取目录失败: ${escapeHtml(message)}</div>`;
      return;
    }
    if (j.error) {
      container.innerHTML = `<div class="err">${escapeHtml(j.error)}</div>`;
      return;
    }

    const entries = j.entries || [];
    container.innerHTML = '';
    buildBreadcrumb(path, which);

    if (!entries.length) {
      container.innerHTML = '<div class="muted-msg">空目录</div>';
      return;
    }

    for (const e of entries) {
      const div = document.createElement('div');
      div.className = 'entry' + (e.is_dir ? ' dir' : ' file');
      div.setAttribute('role', 'listitem');

      const nameEl = document.createElement('div');
      nameEl.className = 'entry-name';
      nameEl.textContent = e.name + (e.is_dir ? '/' : '');

      const actionEl = document.createElement('div');
      actionEl.className = 'entry-meta';
      actionEl.textContent = e.is_dir ? '目录' : '文件';

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

      div.appendChild(nameEl);
      div.appendChild(actionEl);
      container.appendChild(div);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      container.innerHTML = '<div class="err">请求超时（目录较大或挂载点不可用），请重试。</div>';
    } else {
      container.innerHTML = `<div class="err">加载失败: ${escapeHtml(err.message || err)}</div>`;
    }
    console.error('loadEntries error', err);
  } finally {
    if (which === 'src') loadingSrc = false;
    else loadingDst = false;
  }
}

srcUpBtn.onclick = async () => {
  if (!currentSrcPath) return;
  const parent = parentPath(currentSrcPath);
  if (currentSrcRoot && parent.length < currentSrcRoot.length && currentSrcRoot.startsWith(parent)) {
    currentSrcPath = currentSrcRoot;
  } else {
    currentSrcPath = parent;
  }
  await loadEntries(currentSrcPath, 'src');
};

dstUpBtn.onclick = async () => {
  if (!currentDstPath) return;
  const parent = parentPath(currentDstPath);
  if (currentDstRoot && parent.length < currentDstRoot.length && currentDstRoot.startsWith(parent)) {
    currentDstPath = currentDstRoot;
  } else {
    currentDstPath = parent;
  }
  await loadEntries(currentDstPath, 'dst');
};

chooseSrcBtn.onclick = () => {
  const v = currentSrcPath;
  const root = srcRootSelect.value || currentSrcRoot || '/';
  if (!v) {
    toast('请先选择源目录', 'warn');
    return;
  }
  if (srcs.some((s) => s.path === v)) {
    toast('该源目录已在列表中', 'warn');
    return;
  }
  srcs.push({ path: v, root });
  renderLists();
  toast('已加入源目录', 'success');
};

chooseDstBtn.onclick = () => {
  const v = currentDstPath;
  const root = dstRootSelect.value || currentDstRoot || '/';
  if (!v) {
    toast('请先选择目标目录', 'warn');
    return;
  }
  dsts.push({ path: v, root });
  renderLists();
  toast('已加入目标目录', 'success');
};

function renderLists() {
  srcListEl.innerHTML = '';
  dstListEl.innerHTML = '';
  srcCountEl.textContent = `源 ${srcs.length}`;
  dstCountEl.textContent = `目标 ${dsts.length}`;

  srcs.forEach((s, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    pill.innerHTML = `
      <div class="pname">
        <strong>${i + 1}.</strong> ${escapeHtml(s.path)}
        <span class="proot">root: ${escapeHtml(s.root)}</span>
      </div>
      <div class="pactions">
        <button type="button" class="btn btn-mini" data-remove-src="${i}">移除</button>
      </div>`;
    srcListEl.appendChild(pill);
  });

  dsts.forEach((d, i) => {
    const pill = document.createElement('div');
    pill.className = 'pill';
    pill.innerHTML = `
      <div class="pname">
        <strong>${i + 1}.</strong> ${escapeHtml(d.path)}
        <span class="proot">root: ${escapeHtml(d.root)}</span>
      </div>
      <div class="pactions">
        <button type="button" class="btn btn-mini" data-remove-dst="${i}">移除</button>
      </div>`;
    dstListEl.appendChild(pill);
  });

  srcListEl.querySelectorAll('[data-remove-src]').forEach((btn) => {
    btn.onclick = () => {
      const idx = Number(btn.getAttribute('data-remove-src'));
      srcs.splice(idx, 1);
      renderLists();
    };
  });
  dstListEl.querySelectorAll('[data-remove-dst]').forEach((btn) => {
    btn.onclick = () => {
      const idx = Number(btn.getAttribute('data-remove-dst'));
      dsts.splice(idx, 1);
      renderLists();
    };
  });
}

addPairsBtn.onclick = async () => {
  const n = Math.min(srcs.length, dsts.length);
  if (n === 0) {
    toast('至少需要一对源和目标（按索引配对）', 'warn');
    return;
  }

  const mode = document.querySelector('input[name="mode"]:checked')?.value || 'incremental';
  const tasks = [];
  for (let i = 0; i < n; i++) {
    const s = srcs[i];
    const d = dsts[i];
    if (!s || !d) continue;
    if (s.path === d.path) {
      toast(`已跳过相同路径: ${s.path}`, 'warn');
      continue;
    }
    tasks.push({
      src: s.path,
      src_root: s.root,
      dst: d.path,
      dst_root: d.root,
      mode,
    });
  }

  if (!tasks.length) {
    toast('没有可添加的任务', 'warn');
    return;
  }

  addPairsBtn.disabled = true;
  try {
    const res = await fetch('/api/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tasks }),
    });
    const j = await res.json();
    if (res.ok) {
      srcs = srcs.slice(n);
      dsts = dsts.slice(n);
      renderLists();
      loadQueue();
      const skipped = (j.skipped && j.skipped.length) || 0;
      toast(`已添加 ${j.added || 0} 个任务${skipped ? `，跳过 ${skipped} 个` : ''}`, skipped ? 'warn' : 'success');
    } else {
      toast('添加失败: ' + (j.error || JSON.stringify(j)), 'error');
    }
  } catch (err) {
    toast('添加任务失败: ' + (err.message || err), 'error');
  } finally {
    addPairsBtn.disabled = false;
  }
};

clearBtn.onclick = () => {
  srcs = [];
  dsts = [];
  renderLists();
  toast('已清空选择', 'success');
};

clearLogBtn.onclick = () => {
  logEl.textContent = '';
};

async function loadQueue() {
  try {
    const res = await fetch('/api/queue');
    const j = await res.json();
    const items = j.queue || [];
    queueEl.innerHTML = '';
    queueCountEl.textContent = `${items.length} 项`;
    if (!items.length) {
      queueEl.setAttribute('data-empty', '队列为空');
      return;
    }
    queueEl.removeAttribute('data-empty');
    items.forEach((it, idx) => {
      const li = document.createElement('li');
      li.innerHTML = `
        <strong>${idx + 1}.</strong> ${escapeHtml(it.src)}
        <div class="queue-meta">→ ${escapeHtml(it.dst)} · mode=${escapeHtml(it.mode || 'incremental')}</div>`;
      queueEl.appendChild(li);
    });
  } catch (err) {
    queueEl.innerHTML = '<li class="err">无法加载队列</li>';
    queueCountEl.textContent = '错误';
  }
}

function appendLogLine(line) {
  const lines = (logEl.textContent || '').split('\n').filter(Boolean);
  lines.push(line);
  const tail = lines.slice(-MAX_LOG_LINES);
  logEl.textContent = tail.join('\n') + '\n';
  logEl.scrollTop = logEl.scrollHeight;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initLogStream();
  }, 4000);
}

function initLogStream() {
  if (es) {
    try { es.close(); } catch (_) {}
    es = null;
  }

  if (!window.EventSource) {
    setConnectionState('polling', '轮询日志');
    startPollingLogs();
    return;
  }

  try {
    es = new EventSource('/stream');
    setConnectionState('', '连接中');
    es.onopen = () => {
      setConnectionState('online', '实时日志');
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    };
    es.onmessage = (e) => {
      appendLogLine(e.data);
    };
    es.onerror = () => {
      setConnectionState('offline', '连接断开');
      try { es.close(); } catch (_) {}
      es = null;
      startPollingLogs();
      scheduleReconnect();
    };
  } catch (err) {
    console.warn('EventSource init failed', err);
    setConnectionState('polling', '轮询日志');
    startPollingLogs();
  }
}

async function fetchLogsOnce() {
  try {
    const res = await fetch('/api/logs?n=100');
    if (!res.ok) return;
    const j = await res.json();
    const lines = j.lines || [];
    logEl.textContent = lines.join('\n') + (lines.length ? '\n' : '');
    logEl.scrollTop = logEl.scrollHeight;
  } catch (err) {
    console.warn('fetchLogsOnce error', err);
  }
}

function startPollingLogs() {
  setConnectionState('polling', '轮询日志');
  if (pollInterval) return;
  fetchLogsOnce();
  pollInterval = setInterval(fetchLogsOnce, 3000);
}

refreshRootsBtn.onclick = async () => {
  await loadRootsToSelects();
};

window.onload = () => {
  renderLists();
  loadRootsToSelects();
  initLogStream();
  loadQueue();
  setInterval(loadQueue, 5000);
};
