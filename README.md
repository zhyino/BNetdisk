# 假文件入库管理面板（moviepilot-backup-web-v12）

v12 重点修复：
- 避免在应用导入阶段同步加载大量 backup_log 导致首次加载卡顿（现在异步在 worker 线程中加载尾部记录）。
- 增加服务日志文件（service_log.txt），并提供 /api/logs 供前端轮询回退使用，保证日志在 SSE 失效时仍可查看。
- 修复“刷新挂载点”连续点击卡住（前端增加 loading 状态并禁用重复点击）。
- 修复按钮跟随目录滚动问题（按钮不在滚动容器内，前端不可滚动隐藏）。
- 保证目标目录下镜像源目录的完整路径（解决少一级目录的问题）。
- 针对 large backup_log 使用尾部读取，内存友好（可配置）。

## 部署与注意事项
1. 修改 `docker-compose.yml` 的 volumes，把希望在 Web 页面中浏览的宿主机目录映射到容器（示例）：
```yaml
volumes:
  - ./data:/app/data:rw
  - /vol2/1000/Video/115:/115:rw
  - /vol2/1000/Video/Video:/Video:rw
```
2. 启动：
```bash
docker compose up -d --build
```
3. 访问：`http://<服务器IP>:18008/`

### 关于 UID/GID
- 在 `docker-compose.yml` 中直接设置 `UID`/`GID` 环境变量不会改变容器进程的运行用户；我在镜像中加入了 `docker-entrypoint.sh`，当容器以 `root` 启动且设置了 `UID`/`GID` 环境变量时，入口脚本会尝试 `chown /app/data` 到指定的 UID:GID，方便宿主权限对齐。
- 如果你在 compose 中使用了 `user: "1000:1001"` 以非 root 运行容器，则入口脚本无法以非 root 身份执行 chown；在这种情况下请在宿主机上调整文件属主（`chown -R 1000:1001 ./data`）或以 root 启动容器先完成权限设置。

---
