/* BNetdisk frontend – modular, UX-focused */
(() => {
  const cfg = window.__BNETDISK__ || {};
  const $ = (id) => document.getElementById(id);

  const els = {
    srcRootSelect: $('srcRootSelect'),
    dstRootSelect: $('dstRootSelect'),
    srcEntries: $('srcEntries'),
    dstEntries: $('dstEntries'),
    srcBreadcrumb: $('srcBreadcrumb'),
    dstBreadcrumb: $('dstBreadcrumb'),
    srcUpBtn: $('srcUpBtn'),
    dstUpBtn: $('dstUpBtn'),
    refreshRootsBtn: $('refreshRoots'),
    chooseSrcBtn: $('chooseSrcBtn'),
    chooseDstBtn: $('chooseDstBtn'),
    srcListEl: $('srcList'),
    dstListEl: $('dstList'),
    addPairsBtn: $('addPairs'),
    clearBtn: $('clearSelected'),
    queueEl: $('queue'),
    logEl: $('log'),
    srcCountEl: $('srcCount'),
    dstCountEl: $('dstCount'),
    pairCountEl: $('pairCount'),
    queueCountEl: $('queueCount'),
    connectionStatus: $('connectionStatus'),
    connectionText: $('connectionText'),
    clearLogBtn: $('clearLogBtn'),
    copyLogBtn: $('copyLogBtn'),
    toastHost: $('toastHost'),
    srcCurrentPath: $('srcCurrentPath'),
    dstCurrentPath: $('dstCurrentPath'),
    currentTask: $('currentTask'),
    rateText: $('rateText'),
    videoExtHint: $('videoExtHint'),
  };

  const state = {
    srcs: [],
    dsts: [],
    currentSrcPath: null,
    currentDstPath: null,
    currentSrcRoot: null,
    currentDstRoot: null,
    loadingRoots: false,
    loadingSrc: false,
    loadingDst: false,
    es: null,
    pollInterval: null,
    reconnectTimer: null,
  };

  const DEFAULT_TIMEOUT = 8000;
  const MAX_LOG_LINES = 100;

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function toast(message, type = 'info', timeout = 3200) {
    if (!els.toastHost) return console.log(message);
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.textContent = message;
    els.toastHost.appendChild(node);
    setTimeout(() => {
      node.style.opacity = '0';
      node.style.transform = 'translateY(6px)';
      node.style.transition = '0.2s ease';
      setTimeout(() => node.remove(), 220);
    }, timeout);
  }

  function setConnectionState(kind, text) {
    if (!els.connectionStatus || !els.connectionText) return;
    els.connectionStatus.classList.remove('online', 'offline', 'polling');
    if (kind) els.connectionStatus.classList.add(kind);
    els.connectionText.textContent = text;
  }

  function fetchWithTimeout(url, options = {}, timeout = DEFAULT_TIMEOUT) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    return fetch(url, { ...options, signal: controller.signal })
      .finally(() => clearTimeout(timer));
  }

  function parentPath(path) {
    if (!path || path === '/') return '/';
    const cleaned = path.replace(/\/+$/, '');
    const idx = cleaned.lastIndexOf('/');
    if (idx <= 0) return '/';
    return cleaned.slice(0, idx) || '/';
  }

  function setPathChip(el, path) {
    if (!el) return;
    el.textContent = path || '未选择';
    el.title = path || '';
  }

  function buildBreadcrumb(path, which) {
    const host = which === 'src' ? els.srcBreadcrumb : els.dstBreadcrumb;
    const root = which === 'src' ? (state.currentSrcRoot || path) : (state.currentDstRoot || path);
    host.innerHTML = '';

    const parts = [];
    if (path === root || path.startsWith(root + '/') || root === path) {
      parts.push({ label: root, value: root });
      if (path !== root && path.startsWith(root + '/')) {
        const rest = path.slice(root.length).replace(/^\/+/, '');
        let acc = root === '/' ? '' : root;
        rest.split('/').filter(Boolean).forEach((seg) => {
          acc = (acc === '/' ? '' : acc) + '/' + seg;
          if (acc.startsWith('//')) acc = acc.slice(1);
          parts.push({ label: seg, value: acc });
        });
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
          state.currentSrcPath = part.value;
          await loadEntries(part.value, 'src');
        } else {
          state.currentDstPath = part.value;
          await loadEntries(part.value, 'dst');
        }
      };
      host.appendChild(btn);
      if (index < parts.length - 1) {
        const sep = document.createElement('span');
        sep.className = 'crumb-sep';
        sep.textContent = '/';
        host.appendChild(sep);
      }
    });
  }

  async function loadRootsToSelects() {
    if (state.loadingRoots) return;
    state.loadingRoots = true;
    els.refreshRootsBtn.disabled = true;
    const old = els.refreshRootsBtn.textContent;
    els.refreshRootsBtn.textContent = '刷新中...';
    try {
      els.srcRootSelect.innerHTML = '<option>加载中...</option>';
      els.dstRootSelect.innerHTML = '<option>加载中...</option>';
      const res = await fetchWithTimeout('/api/roots');
      if (!res.ok) throw new Error('加载挂载点失败');
      const data = await res.json();
      const roots = data.roots || [];
      populateRootSelect(els.srcRootSelect, roots, 'src');
      populateRootSelect(els.dstRootSelect, roots, 'dst');
      if (roots.length) {
        state.currentSrcRoot = roots[0];
        state.currentDstRoot = roots[0];
        state.currentSrcPath = roots[0];
        state.currentDstPath = roots[0];
        await Promise.all([
          loadEntries(state.currentSrcPath, 'src'),
          loadEntries(state.currentDstPath, 'dst'),
        ]);
        toast(`已加载 ${roots.length} 个挂载点`, 'success');
      } else {
        const msg = '<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
        els.srcEntries.innerHTML = msg;
        els.dstEntries.innerHTML = msg;
        toast('未发现挂载点', 'warn');
      }
    } catch (err) {
      els.srcRootSelect.innerHTML = '<option>加载失败</option>';
      els.dstRootSelect.innerHTML = '<option>加载失败</option>';
      const msg = '<div class="err">加载挂载点失败，请点击“刷新挂载点”或检查 volumes。</div>';
      els.srcEntries.innerHTML = msg;
      els.dstEntries.innerHTML = msg;
      toast('加载挂载点失败', 'error');
      console.error(err);
    } finally {
      state.loadingRoots = false;
      els.refreshRootsBtn.disabled = false;
      els.refreshRootsBtn.textContent = old || '刷新挂载点';
    }
  }

  function populateRootSelect(selectEl, roots, which) {
    selectEl.innerHTML = '';
    roots.forEach((root) => {
      const opt = document.createElement('option');
      opt.value = root;
      opt.textContent = root;
      selectEl.appendChild(opt);
    });
    selectEl.onchange = async () => {
      const value = selectEl.value;
      if (which === 'src') {
        state.currentSrcRoot = value;
        state.currentSrcPath = value;
        await loadEntries(value, 'src');
      } else {
        state.currentDstRoot = value;
        state.currentDstPath = value;
        await loadEntries(value, 'dst');
      }
    };
  }

  async function loadEntries(path, which) {
    if (which === 'src' && state.loadingSrc) return;
    if (which === 'dst' && state.loadingDst) return;
    if (which === 'src') state.loadingSrc = true;
    else state.loadingDst = true;

    const container = which === 'src' ? els.srcEntries : els.dstEntries;
    setPathChip(which === 'src' ? els.srcCurrentPath : els.dstCurrentPath, path);
    container.innerHTML = '<div class="muted-msg">加载中...</div>';

    try {
      const res = await fetchWithTimeout('/api/listdir?path=' + encodeURIComponent(path));
      const raw = await res.text();
      let data = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch (_) {
        data = { error: raw || res.statusText || 'invalid response' };
      }
      if (!res.ok) {
        container.innerHTML = `<div class="err">读取目录失败: ${escapeHtml(data.error || raw || res.statusText)}</div>`;
        return;
      }
      if (data.error) {
        container.innerHTML = `<div class="err">${escapeHtml(data.error)}</div>`;
        return;
      }

      const entries = data.entries || [];
      container.innerHTML = '';
      buildBreadcrumb(path, which);

      if (!entries.length) {
        container.innerHTML = '<div class="muted-msg">空目录</div>';
        return;
      }

      entries.forEach((entry) => {
        const row = document.createElement('div');
        const isDir = !!entry.is_dir;
        const isVideo = !!entry.is_video;
        row.className = 'entry ' + (isDir ? 'dir' : (isVideo ? 'file video' : 'file'));
        row.setAttribute('role', 'listitem');

        const name = document.createElement('div');
        name.className = 'entry-name';
        name.textContent = entry.name + (isDir ? '/' : '');

        const meta = document.createElement('div');
        meta.className = 'entry-meta';
        meta.textContent = isDir ? '目录' : (isVideo ? '视频' : '文件');

        if (isDir) {
          row.onclick = async () => {
            if (which === 'src') {
              state.currentSrcPath = entry.path;
              await loadEntries(entry.path, 'src');
            } else {
              state.currentDstPath = entry.path;
              await loadEntries(entry.path, 'dst');
            }
          };
        }

        row.appendChild(name);
        row.appendChild(meta);
        container.appendChild(row);
      });
    } catch (err) {
      if (err.name === 'AbortError') {
        container.innerHTML = '<div class="err">请求超时（目录较大或挂载点不可用），请重试。</div>';
      } else {
        container.innerHTML = `<div class="err">加载失败: ${escapeHtml(err.message || err)}</div>`;
      }
      console.error(err);
    } finally {
      if (which === 'src') state.loadingSrc = false;
      else state.loadingDst = false;
    }
  }

  function renderLists() {
    els.srcListEl.innerHTML = '';
    els.dstListEl.innerHTML = '';
    els.srcCountEl.textContent = `源 ${state.srcs.length}`;
    els.dstCountEl.textContent = `目标 ${state.dsts.length}`;
    els.pairCountEl.textContent = `可配对 ${Math.min(state.srcs.length, state.dsts.length)}`;

    state.srcs.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'item';
      row.innerHTML = `
        <div class="item-main">
          <div class="item-title"><strong>${index + 1}.</strong> ${escapeHtml(item.path)}</div>
          <div class="item-sub">root: ${escapeHtml(item.root)}</div>
        </div>
        <button type="button" class="btn mini" data-remove-src="${index}">移除</button>`;
      els.srcListEl.appendChild(row);
    });

    state.dsts.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'item';
      row.innerHTML = `
        <div class="item-main">
          <div class="item-title"><strong>${index + 1}.</strong> ${escapeHtml(item.path)}</div>
          <div class="item-sub">root: ${escapeHtml(item.root)}</div>
        </div>
        <button type="button" class="btn mini" data-remove-dst="${index}">移除</button>`;
      els.dstListEl.appendChild(row);
    });

    els.srcListEl.querySelectorAll('[data-remove-src]').forEach((btn) => {
      btn.onclick = () => {
        state.srcs.splice(Number(btn.getAttribute('data-remove-src')), 1);
        renderLists();
      };
    });
    els.dstListEl.querySelectorAll('[data-remove-dst]').forEach((btn) => {
      btn.onclick = () => {
        state.dsts.splice(Number(btn.getAttribute('data-remove-dst')), 1);
        renderLists();
      };
    });
  }

  function appendLogLine(line) {
    const lines = (els.logEl.textContent || '').split('\n').filter(Boolean);
    lines.push(line);
    const tail = lines.slice(-MAX_LOG_LINES);
    els.logEl.textContent = tail.join('\n') + '\n';
    els.logEl.scrollTop = els.logEl.scrollHeight;
  }

  async function loadQueue() {
    try {
      const res = await fetch('/api/queue');
      const data = await res.json();
      const items = data.queue || [];
      els.queueEl.innerHTML = '';
      els.queueCountEl.textContent = `${items.length} 项`;

      if (data.current) {
        els.currentTask.classList.remove('hidden');
        els.currentTask.innerHTML = `
          <strong>正在执行</strong><br>
          ${escapeHtml(data.current.src)}<br>
          → ${escapeHtml(data.current.dst)}
          <div class="queue-meta">mode=${escapeHtml(data.current.mode || 'incremental')}</div>`;
      } else {
        els.currentTask.classList.add('hidden');
        els.currentTask.innerHTML = '';
      }

      if (!items.length) {
        els.queueEl.setAttribute('data-empty', '队列为空，添加任务后会显示在这里');
        return;
      }
      els.queueEl.removeAttribute('data-empty');
      items.forEach((item, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
          <strong>${index + 1}.</strong> ${escapeHtml(item.src)}
          <div class="queue-meta">→ ${escapeHtml(item.dst)} · mode=${escapeHtml(item.mode || 'incremental')}</div>`;
        els.queueEl.appendChild(li);
      });
    } catch (_) {
      els.queueEl.innerHTML = '<li class="err">无法加载队列</li>';
      els.queueCountEl.textContent = '错误';
    }
  }

  async function loadMeta() {
    try {
      const res = await fetch('/api/meta');
      if (!res.ok) return;
      const data = await res.json();
      if (els.rateText) els.rateText.textContent = `速率 ${data.backup_rate || '--'}/s`;
      if (els.videoExtHint) {
        const exts = (data.video_exts || cfg.videoExts || []).slice(0, 8).join(' ');
        els.videoExtHint.textContent = exts ? `如 ${exts}...` : '仅视频';
        els.videoExtHint.title = (data.video_exts || []).join(', ');
      }
    } catch (_) {
      /* ignore */
    }
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) return;
    state.reconnectTimer = setTimeout(() => {
      state.reconnectTimer = null;
      initLogStream();
    }, 4000);
  }

  function initLogStream() {
    if (state.es) {
      try { state.es.close(); } catch (_) {}
      state.es = null;
    }
    if (!window.EventSource) {
      setConnectionState('polling', '轮询日志');
      startPollingLogs();
      return;
    }
    try {
      state.es = new EventSource('/stream');
      setConnectionState('', '连接中');
      state.es.onopen = () => {
        setConnectionState('online', '实时日志');
        if (state.pollInterval) {
          clearInterval(state.pollInterval);
          state.pollInterval = null;
        }
      };
      state.es.onmessage = (event) => appendLogLine(event.data);
      state.es.onerror = () => {
        setConnectionState('offline', '连接断开');
        try { state.es.close(); } catch (_) {}
        state.es = null;
        startPollingLogs();
        scheduleReconnect();
      };
    } catch (err) {
      console.warn(err);
      setConnectionState('polling', '轮询日志');
      startPollingLogs();
    }
  }

  async function fetchLogsOnce() {
    try {
      const res = await fetch('/api/logs?n=100');
      if (!res.ok) return;
      const data = await res.json();
      const lines = data.lines || [];
      els.logEl.textContent = lines.join('\n') + (lines.length ? '\n' : '');
      els.logEl.scrollTop = els.logEl.scrollHeight;
    } catch (_) {
      /* ignore */
    }
  }

  function startPollingLogs() {
    setConnectionState('polling', '轮询日志');
    if (state.pollInterval) return;
    fetchLogsOnce();
    state.pollInterval = setInterval(fetchLogsOnce, 3000);
  }

  // Events
  els.srcUpBtn.onclick = async () => {
    if (!state.currentSrcPath) return;
    let parent = parentPath(state.currentSrcPath);
    if (state.currentSrcRoot && parent.length < state.currentSrcRoot.length && state.currentSrcRoot.startsWith(parent)) {
      parent = state.currentSrcRoot;
    }
    state.currentSrcPath = parent;
    await loadEntries(parent, 'src');
  };

  els.dstUpBtn.onclick = async () => {
    if (!state.currentDstPath) return;
    let parent = parentPath(state.currentDstPath);
    if (state.currentDstRoot && parent.length < state.currentDstRoot.length && state.currentDstRoot.startsWith(parent)) {
      parent = state.currentDstRoot;
    }
    state.currentDstPath = parent;
    await loadEntries(parent, 'dst');
  };

  els.chooseSrcBtn.onclick = () => {
    const path = state.currentSrcPath;
    const root = els.srcRootSelect.value || state.currentSrcRoot || '/';
    if (!path) return toast('请先选择源目录', 'warn');
    if (state.srcs.some((item) => item.path === path)) return toast('该源目录已在列表中', 'warn');
    state.srcs.push({ path, root });
    renderLists();
    toast('已加入源目录', 'success');
  };

  els.chooseDstBtn.onclick = () => {
    const path = state.currentDstPath;
    const root = els.dstRootSelect.value || state.currentDstRoot || '/';
    if (!path) return toast('请先选择目标目录', 'warn');
    state.dsts.push({ path, root });
    renderLists();
    toast('已加入目标目录', 'success');
  };

  els.addPairsBtn.onclick = async () => {
    const n = Math.min(state.srcs.length, state.dsts.length);
    if (!n) return toast('至少需要一对源和目标（按索引配对）', 'warn');

    const mode = document.querySelector('input[name="mode"]:checked')?.value || 'incremental';
    const tasks = [];
    for (let i = 0; i < n; i += 1) {
      const src = state.srcs[i];
      const dst = state.dsts[i];
      if (!src || !dst) continue;
      if (src.path === dst.path) {
        toast(`已跳过相同路径: ${src.path}`, 'warn');
        continue;
      }
      tasks.push({
        src: src.path,
        src_root: src.root,
        dst: dst.path,
        dst_root: dst.root,
        mode,
      });
    }
    if (!tasks.length) return toast('没有可添加的任务', 'warn');

    els.addPairsBtn.disabled = true;
    try {
      const res = await fetch('/api/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tasks, videos_only: true }),
      });
      const data = await res.json();
      if (res.ok) {
        state.srcs = state.srcs.slice(n);
        state.dsts = state.dsts.slice(n);
        renderLists();
        loadQueue();
        const skipped = (data.skipped && data.skipped.length) || 0;
        toast(`已添加 ${data.added || 0} 个任务${skipped ? `，跳过 ${skipped} 个` : ''}`, skipped ? 'warn' : 'success');
      } else {
        toast('添加失败: ' + (data.error || JSON.stringify(data)), 'error');
      }
    } catch (err) {
      toast('添加任务失败: ' + (err.message || err), 'error');
    } finally {
      els.addPairsBtn.disabled = false;
    }
  };

  els.clearBtn.onclick = () => {
    state.srcs = [];
    state.dsts = [];
    renderLists();
    toast('已清空选择', 'success');
  };

  els.clearLogBtn.onclick = () => {
    els.logEl.textContent = '';
  };

  els.copyLogBtn.onclick = async () => {
    const text = els.logEl.textContent || '';
    if (!text.trim()) return toast('日志为空', 'warn');
    try {
      await navigator.clipboard.writeText(text);
      toast('日志已复制', 'success');
    } catch (_) {
      toast('复制失败，请手动选择日志文本', 'error');
    }
  };

  els.refreshRootsBtn.onclick = () => loadRootsToSelects();

  window.addEventListener('load', () => {
    renderLists();
    loadMeta();
    loadRootsToSelects();
    initLogStream();
    loadQueue();
    setInterval(loadQueue, 4000);
  });
})();
