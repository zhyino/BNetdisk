# moviepilot-backup-web-v3

功能亮点：
- 中文卡片化界面：左侧浏览选择（选择由 docker-compose 映射到容器的目录），右侧实时日志
- 支持多选源与多选目标；按索引配对或单目标应用于所有源
- 默认过滤图片及 .nfo 文件（不可关闭）
- 创建 1KB 占位文件（不复制原始文件），并以原子方式持久化备份索引到 ./data/backup_log.txt
- 自动发现容器内挂载点（/proc/mounts），也可通过环境变量 ALLOWED_ROOTS 指定

部署说明：
1. 编辑 `docker-compose.yml`，在 `volumes` 中添加你想映射的宿主机目录，例如：
   ```yaml
   - /path/on/host/movies:/mnt/inputs:rw
   - /path/on/host/backups:/mnt/outputs:rw
   ```
   这些路径会出现在 Web 界面的“挂载根”列表中，供你浏览与选择。
2. 创建并调整权限：
   ```bash
   mkdir -p data
   touch data/backup_log.txt
   chown -R 1000:1001 data || true
   ```
3. 启动服务：
   ```bash
   docker-compose up -d --build
   ```
4. 访问：`http://<server-ip>:18008`

注意：页面只能浏览到容器内可访问的挂载目录；如果某个宿主目录没有出现，请确保已在 compose 中映射并重启容器。
