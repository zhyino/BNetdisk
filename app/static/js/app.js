
// minimal front-end logic (buffered SSE flush + listdir truncated notice)
let messagesBuffer = []; let bufferFlushInterval = null; const MAX_DISPLAY_LINES = 2000;
const logEl = document.getElementById('log');
function flushBuffer(){
  if (!logEl) return;
  if (messagesBuffer.length === 0) return;
  const toAdd = messagesBuffer.splice(0, messagesBuffer.length);
  const text = toAdd.join('\n') + '\n';
  const lines = (logEl.textContent + text).split('\n');
  if (lines.length > MAX_DISPLAY_LINES){
    const tail = lines.slice(-MAX_DISPLAY_LINES);
    logEl.textContent = tail.join('\n') + '\n';
  } else {
    logEl.textContent += text;
  }
  logEl.scrollTop = logEl.scrollHeight;
}
function initLogStream(){
  if (!!window.EventSource){
    try {
      const es = new EventSource('/stream');
      es.onmessage = (e)=>{ messagesBuffer.push(e.data); };
      es.onerror = ()=>{ flushBuffer(); };
    } catch(e){ /* fallback */ }
  }
  if (!bufferFlushInterval) bufferFlushInterval = setInterval(flushBuffer, 300);
}
window.onload = ()=>{ initLogStream(); };
