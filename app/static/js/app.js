
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

let srcs = [], dsts = [];
let currentSrcPath = null, currentDstPath = null;
let loadingRoots=false, loadingSrc=false, loadingDst=false;
const DEFAULT_TIMEOUT = 8000;
let es=null, pollInterval=null;

function fetchWithTimeout(url, opts={}, timeout=DEFAULT_TIMEOUT){
  const controller = new AbortController();
  const id = setTimeout(()=>controller.abort(), timeout);
  return fetch(url, Object.assign({}, opts, {signal: controller.signal})).finally(()=>clearTimeout(id));
}

async function loadRoots(){
  if(loadingRoots) return;
  loadingRoots=true;
  refreshRootsBtn.disabled=true; refreshRootsBtn.textContent='刷新中...';
  try{
    srcRootSelect.innerHTML='<option>加载中...</option>';
    dstRootSelect.innerHTML='<option>加载中...</option>';
    const res = await fetchWithTimeout('/api/roots');
    if(!res.ok) throw new Error('加载挂载点失败');
    const data = await res.json();
    const roots = data.roots || [];
    populateRoot(srcRootSelect, roots);
    populateRoot(dstRootSelect, roots);
    if(roots.length){
      currentSrcPath = roots[0]; currentDstPath = roots[0];
      await Promise.all([loadEntries(currentSrcPath,'src'), loadEntries(currentDstPath,'dst')]);
    } else {
      srcEntries.innerHTML='<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
      dstEntries.innerHTML='<div class="err">未发现挂载点，请在 docker-compose 中映射宿主目录并重启容器。</div>';
    }
  }catch(err){
    srcEntries.innerHTML='<div class="err">加载挂载点失败</div>';
    dstEntries.innerHTML='<div class="err">加载挂载点失败</div>';
    console.error(err);
  }finally{
    loadingRoots=false; refreshRootsBtn.disabled=false; refreshRootsBtn.textContent='刷新挂载点';
  }
}

function populateRoot(sel, roots){
  sel.innerHTML=''; roots.forEach(r=>{ const opt=document.createElement('option'); opt.value=r; opt.innerText=r; sel.appendChild(opt);} )
  sel.onchange = async ()=>{ const v=sel.value; if(sel===srcRootSelect){ currentSrcPath=v; await loadEntries(currentSrcPath,'src'); } else { currentDstPath=v; await loadEntries(currentDstPath,'dst'); } }
}

async function loadEntries(path, which){
  if(which==='src' && loadingSrc) return;
  if(which==='dst' && loadingDst) return;
  if(which==='src') loadingSrc=true; else loadingDst=true;
  const container = which==='src' ? srcEntries : dstEntries;
  const breadcrumb = which==='src' ? srcBreadcrumb : dstBreadcrumb;
  container.innerHTML='加载中...';
  try{
    const res = await fetchWithTimeout('/api/listdir?path='+encodeURIComponent(path));
    if(!res.ok){ container.innerHTML='<div class="err">读取目录失败</div>'; return; }
    const j = await res.json();
    if(j.error){ container.innerHTML='<div class="err">'+j.error+'</div>'; return; }
    const entries = j.entries || [];
    container.innerHTML=''; breadcrumb.innerHTML='';
    const rootBtn = document.createElement('button'); rootBtn.className='crumb'; rootBtn.innerText=path; rootBtn.onclick = async ()=>{ if(which==='src'){ currentSrcPath=path; await loadEntries(currentSrcPath,'src'); } else { currentDstPath=path; await loadEntries(currentDstPath,'dst'); } }; breadcrumb.appendChild(rootBtn);
    for(const e of entries){
      const div = document.createElement('div'); div.className='entry'+(e.is_dir ? ' dir' : ' file');
      const nameEl = document.createElement('div'); nameEl.innerText = e.name + (e.is_dir ? '/' : '');
      div.appendChild(nameEl);
      if(e.is_dir){
        div.onclick = async ()=>{ if(which==='src'){ currentSrcPath = e.path; await loadEntries(currentSrcPath,'src'); } else { currentDstPath = e.path; await loadEntries(currentDstPath,'dst'); } }
      }
      container.appendChild(div);
    }
  }catch(err){
    container.innerHTML='<div class="err">加载失败</div>';
    console.error(err);
  }finally{
    if(which==='src') loadingSrc=false; else loadingDst=false;
  }
}

srcUpBtn.onclick = async ()=>{ if(!currentSrcPath) return; const parent = currentSrcPath==='/':'/' : currentSrcPath.split('/').slice(0,-1).join('/')||'/'; currentSrcPath=parent; await loadEntries(currentSrcPath,'src'); }
dstUpBtn.onclick = async ()=>{ if(!currentDstPath) return; const parent = currentDstPath==='/':'/' : currentDstPath.split('/').slice(0,-1).join('/')||'/'; currentDstPath=parent; await loadEntries(currentDstPath,'dst'); }

chooseSrcBtn.onclick = ()=>{ const v=currentSrcPath; const root = srcRootSelect.value||'/'; if(v) srcs.push({path:v, root:root}); renderLists(); }
chooseDstBtn.onclick = ()=>{ const v=currentDstPath; const root = dstRootSelect.value||'/'; if(v) dsts.push({path:v, root:root}); renderLists(); }

function renderLists(){ srcListEl.innerHTML=''; srcs.forEach((s,i)=>{ const pill=document.createElement('div'); pill.className='pill'; pill.innerHTML = `<div class="pname">${i+1}. ${s.path} (${s.root})</div><div class="pactions"><button class="small" onclick="removeSrc(${i})">移除</button></div>`; srcListEl.appendChild(pill); }); dstListEl.innerHTML=''; dsts.forEach((d,i)=>{ const pill=document.createElement('div'); pill.className='pill'; pill.innerHTML = `<div class="pname">${i+1}. ${d.path} (${d.root})</div><div class="pactions"><button class="small" onclick="removeDst(${i})">移除</button></div>`; dstListEl.appendChild(pill); }); }
window.removeSrc = (i)=>{ srcs.splice(i,1); renderLists(); }
window.removeDst = (i)=>{ dsts.splice(i,1); renderLists(); }

addPairsBtn.onclick = async ()=>{
  const n = Math.min(srcs.length, dsts.length);
  if(n===0){ alert('至少需要一对源和目标（按索引配对）'); return; }
  const mode = document.querySelector('input[name="mode"]:checked').value || 'incremental';
  const tasks = [];
  for(let i=0;i<n;i++){ const s=srcs[i], d=dsts[i]; if(!s||!d) continue; if(s.path===d.path){ alert('警告：源和目标相同，已跳过: '+s.path); continue; } tasks.push({src:s.path, dst:d.path, mode}); }
  if(tasks.length===0){ alert('没有可添加的任务'); return; }
  try{
    const res = await fetch('/api/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tasks})});
    const j = await res.json();
    if(res.ok){ srcs=srcs.slice(n); dsts=dsts.slice(n); renderLists(); loadQueue(); if(j.skipped && j.skipped.length){ alert('部分任务被跳过，查看日志'); } }
    else { alert('添加失败:'+JSON.stringify(j)); }
  }catch(err){ alert('添加失败:'+err.message); }
}

clearBtn.onclick = ()=>{ srcs=[]; dsts=[]; renderLists(); }
async function loadQueue(){ try{ const res = await fetch('/api/queue'); const j = await res.json(); queueEl.innerHTML=''; j.queue.forEach((it,idx)=>{ const li=document.createElement('li'); li.innerText = `${idx+1}. ${it.src} → ${it.dst} (mode=${it.mode||'incremental'})`; queueEl.appendChild(li); }); }catch(err){ queueEl.innerHTML='<li class="err">无法加载队列</li>'; } }

function initLogStream(){
  if(!!window.EventSource){
    try{
      es = new EventSource('/stream');
      es.onmessage = (e)=>{
        const cur = (logEl.textContent || '').split('\\n').filter(Boolean);
        cur.push(e.data);
        const tail = cur.slice(-100);
        logEl.textContent = tail.join('\\n') + '\\n';
        logEl.scrollTop = logEl.scrollHeight;
      };
      es.onerror = (e)=>{
        console.warn('ES error', e);
        if(es){ try{ es.close(); } catch(e){} es=null; }
        startPollLogs();
      };
    }catch(err){
      startPollLogs();
    }
  }else startPollLogs();
}

async function fetchLogsOnce(){
  try{
    const res = await fetch('/api/logs?n=100');
    if(!res.ok) return;
    const j = await res.json();
    const lines = j.lines || [];
    logEl.textContent = lines.join('\\n') + (lines.length ? '\\n' : '');
    logEl.scrollTop = logEl.scrollHeight;
  }catch(err){ console.warn('fetchLogsOnce', err); }
}

function startPollLogs(){
  if(pollInterval) return;
  fetchLogsOnce();
  pollInterval = setInterval(fetchLogsOnce, 3000);
}

refreshRootsBtn.onclick = async ()=>{ await loadRoots(); }
window.onload = ()=>{ loadRoots(); initLogStream(); loadQueue(); setInterval(loadQueue, 5000); }
