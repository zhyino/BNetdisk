# moviepilot-backup-web-v4

更新说明：
- 顶栏新增横向快速选择区：左右两个下拉（根路径 + 子目录），便于直接把映射根或其子目录设为 源/目标。
- 如果你在 docker-compose 中映射了宿主目录到容器根（如 `/vol2/...:/115` 或 `/vol2/...:/Video`），它们会出现在下拉中，可以直接选择 `/115` 或 `/Video` 本身作为路径。
- 默认过滤图片和 .nfo 文件（不可关闭）。

部署步骤：
1. 编辑 `docker-compose.yml`，在 `volumes` 中添加你要暴露到容器的宿主机路径（示例已注释）。
2. 准备 data 目录并设置权限（UID 1000）:
   ```bash
   mkdir -p data
   touch data/backup_log.txt
   chown -R 1000:1001 data || true
   ```
3. 启动：`docker-compose up -d --build`
4. 访问：`http://<server-ip>:18008`

技术注意事项：
- 后端使用 Python 3.11 + Flask 2.2.5 + Gunicorn 20.1.0（在 requirements.txt 中指定），代码已检查常见的兼容性和逻辑问题（缩进、路径白名单、原子写入、SSE 客户端管理等）。
- 如果某个挂载未出现在列表，确认该路径已在 compose 中映射并重启容器（容器读取 /proc/mounts 动态发现挂载点）。
