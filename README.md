# moviepilot-backup-web-v5

本次改动：
- 移除了深度文件浏览器（因为你觉得无用），保留快速选择（左右两组下拉），可以直接选择挂载根或其一级子目录。
- 修复布局：左侧为固定宽度面板（不会被日志区域挤压），右侧日志区域自适应。
- 增加本地与服务器双重校验：当 源 == 目标 时，客户端会提示并跳过；服务器端也会拒绝相同路径任务并返回跳过原因，同时在日志中打印 WARN。
- 继续默认过滤图片和 .nfo 文件（不可关闭），使用 1KB 占位文件表示备份（按原子操作写入）。

快速部署：
1. 在 `docker-compose.yml` 的 volumes 中添加你的宿主机挂载（示例已注释），例如：
   - /vol2/1000/Video/115:/115:rw
   - /vol2/1000/Video/Video:/Video:rw
2. 准备 data 目录并设置写权限（UID 1000）：
   ```bash
   mkdir -p data
   touch data/backup_log.txt
   chown -R 1000:1001 data || true
   ```
3. 启动：`docker-compose up -d --build`
4. 访问：`http://<host>:18008`

兼容性说明：
- Python 3.11 + Flask 2.2.5 + Gunicorn 20.1.0，均已在 requirements.txt 指定。
- 代码已检查缩进、异常处理、路径白名单、SSE 客户端注册/注销、原子写入、并发锁等常见问题。
