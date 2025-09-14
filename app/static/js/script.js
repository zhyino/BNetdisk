document.addEventListener('DOMContentLoaded', function() {
    // 初始化Socket.IO
    const socket = io();
    
    // DOM元素
    const srcDirInput = document.getElementById('srcDir');
    const destDirInput = document.getElementById('destDir');
    const addDirBtn = document.getElementById('addDirBtn');
    const directoryList = document.getElementById('directoryList');
    const startBackupBtn = document.getElementById('startBackupBtn');
    const filterImagesCheckbox = document.getElementById('filterImages');
    const filterNfoCheckbox = document.getElementById('filterNfo');
    const logContainer = document.getElementById('logContainer');
    
    // 加载已添加的目录对
    function loadDirectoryPairs() {
        fetch('/get_jobs')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success' && data.jobs.length > 0) {
                    directoryList.innerHTML = '';
                    data.jobs.forEach(job => {
                        addDirectoryItemToDOM(job);
                    });
                }
            })
            .catch(error => console.error('加载目录对失败:', error));
    }
    
    // 添加目录对到DOM
    function addDirectoryItemToDOM(job) {
        const dirItem = document.createElement('div');
        dirItem.className = 'directory-item';
        dirItem.dataset.id = job.id;
        
        const pathsDiv = document.createElement('div');
        pathsDiv.className = 'directory-paths';
        pathsDiv.innerHTML = `
            <strong>源目录:</strong> ${job.src_dir}<br>
            <strong>目标目录:</strong> ${job.dest_dir}
        `;
        
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-btn';
        removeBtn.textContent = '移除';
        removeBtn.addEventListener('click', function() {
            removeDirectoryPair(job.id);
            dirItem.remove();
            checkEmptyState();
        });
        
        dirItem.appendChild(pathsDiv);
        dirItem.appendChild(removeBtn);
        directoryList.appendChild(dirItem);
        
        checkEmptyState();
    }
    
    // 检查是否为空状态
    function checkEmptyState() {
        if (directoryList.children.length === 0) {
            directoryList.innerHTML = '<div class="empty-state">暂无目录对，请添加</div>';
        }
    }
    
    // 添加目录对
    addDirBtn.addEventListener('click', function() {
        const srcDir = srcDirInput.value.trim();
        const destDir = destDirInput.value.trim();
        
        if (!srcDir || !destDir) {
            alert('源目录和目标目录不能为空');
            return;
        }
        
        fetch('/add_directory_pair', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ src_dir: srcDir, dest_dir: destDir })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                addDirectoryItemToDOM(data.job);
                srcDirInput.value = '';
                destDirInput.value = '';
            } else {
                alert(data.message);
            }
        })
        .catch(error => console.error('添加目录对失败:', error));
    });
    
    // 移除目录对
    function removeDirectoryPair(jobId) {
        fetch('/remove_job', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ job_id: jobId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                alert(data.message);
            }
        })
        .catch(error => console.error('移除目录对失败:', error));
    }
    
    // 开始备份
    startBackupBtn.addEventListener('click', function() {
        // 清空日志
        logContainer.innerHTML = '';
        
        // 发送备份请求
        socket.emit('start_backup', {
            filter_images: filterImagesCheckbox.checked,
            filter_nfo: filterNfoCheckbox.checked
        });
        
        // 禁用按钮防止重复点击
        startBackupBtn.disabled = true;
        startBackupBtn.textContent = '备份中...';
    });
    
    // 接收日志信息
    socket.on('backup_log', function(data) {
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.textContent = `[${new Date().toLocaleTimeString()}] ${data.message}`;
        logContainer.appendChild(logEntry);
        // 滚动到底部
        logContainer.scrollTop = logContainer.scrollHeight;
    });
    
    // 备份完成
    socket.on('backup_complete', function(data) {
        startBackupBtn.disabled = false;
        startBackupBtn.textContent = '开始备份';
    });
    
    // 初始加载
    loadDirectoryPairs();
});
