let messagesBuffer = []; 
let bufferFlushInterval = null; 
const MAX_DISPLAY_LINES = 200;  // 只显示最新200行日志
const logEl = document.getElementById('log');
const queueSizeEl = document.getElementById('queue-size');

function flushBuffer() {
    if (!logEl) return;
    if (messagesBuffer.length === 0) return;
    
    const toAdd = messagesBuffer.splice(0, messagesBuffer.length);
    const currentContent = logEl.textContent;
    const newContent = currentContent + toAdd.join('\n') + '\n';
    
    // 按行分割并保留最后MAX_DISPLAY_LINES行
    const lines = newContent.split('\n');
    if (lines.length > MAX_DISPLAY_LINES) {
        const tailLines = lines.slice(-MAX_DISPLAY_LINES);
        logEl.textContent = tailLines.join('\n') + '\n';
    } else {
        logEl.textContent = newContent;
    }
    
    // 自动滚动到底部
    logEl.scrollTop = logEl.scrollHeight;
}

function updateQueueSize() {
    fetch('/api/queue')
        .then(response => response.json())
        .then(data => {
            if (queueSizeEl) {
                queueSizeEl.textContent = data.queue_size;
            }
        })
        .catch(error => console.error('Failed to update queue size:', error));
}

function initLogStream() {
    if (!!window.EventSource) {
        try {
            const es = new EventSource('/stream');
            
            es.onmessage = (e) => {
                // 过滤空的keepalive消息
                if (e.data && e.data !== ': keepalive') {
                    try {
                        // 尝试解析JSON
                        const data = JSON.parse(e.data);
                        messagesBuffer.push(data);
                    } catch (err) {
                        // 如果不是JSON，直接作为文本处理
                        messagesBuffer.push(e.data);
                    }
                }
            };
            
            es.onerror = () => {
                console.error('EventSource error, reconnecting...');
                es.close();
                setTimeout(initLogStream, 5000);
            };
        } catch (e) {
            console.error('Failed to initialize EventSource:', e);
        }
    }
    
    // 设置缓冲区刷新间隔
    if (!bufferFlushInterval) {
        bufferFlushInterval = setInterval(flushBuffer, 500);
    }
    
    // 定期更新队列大小
    setInterval(updateQueueSize, 3000);
    updateQueueSize(); // 立即更新一次
}

// 页面卸载时清理
window.addEventListener('beforeunload', () => {
    if (bufferFlushInterval) {
        clearInterval(bufferFlushInterval);
    }
});

// 页面加载完成后初始化
window.onload = () => {
    // 初始加载最新日志
    fetch('/api/logs?n=' + MAX_DISPLAY_LINES)
        .then(response => response.json())
        .then(data => {
            if (data.logs && data.logs.length > 0) {
                messagesBuffer = data.logs;
                flushBuffer();
            }
        })
        .catch(error => console.error('Failed to load initial logs:', error))
        .finally(() => {
            initLogStream();
        });
};
