# moviepilot-backup-web-v9（基于 cnlaok 的 BNetdisk.py 扩展）

原始项目： https://github.com/cnlaok/BNetdisk.py  
本仓库为在原作者项目基础上的**扩展版本（v9）**，增加了 Web 面板、按索引配对的批量任务加入、任意深度目录选择、增量/全量两种备份模式、占位文件速率限制等功能。

## 主要功能（扩展点）
- Web 面板（中文 UI）："假文件入库管理面板"，支持逐级浏览宿主机映射到容器的目录并选择任意深度的子目录作为源/目标。
- 按索引配对：第1个源→第1个目标、第2个源→第2个目标，目标允许重复添加以便复用。
- 备份模式：增量（incremental，参考 backup_log.txt，只生成新增占位文件）与全量（full，忽略 backup_log.txt，全部重新生成并覆盖占位文件）。
- 占位文件生成行为：在目标下**先创建与源目录相同的多级子目录结构**（例如 源 `/mnt/Video/影音库/season1` → 目标 `/115` 会创建 `/115/影音库/season1/...`），然后在对应目录下生成 1KB 的占位文件（原子写入）。
- 速率限制：通过 `BACKUP_RATE` 环境变量限制每秒生成占位文件的速率，默认 20 ops/sec，避免对源盘造成高 IO 压力。
- 动态挂载点发现与更鲁棒的目录读取：`/api/roots` 会动态返回当前可用挂载点，`/api/listdir` 在 `scandir` 失败时回退到 `listdir`，避免部分目录异常导致界面失效。
- 服务端日志通过 SSE（Server-Sent Events）实时推送到前端日志面板，便于跟踪执行情况。

## 与原作者保留/兼容性说明
- 本扩展基于原作者项目的实现进行拓展，保留了部分核心备份逻辑，但将其包装为带 Web 面板的容器化服务，便于使用和部署。感谢原作者的工作。

## 快速部署（Linux + Docker Compose）
1. 克隆仓库到服务器：
```bash
git clone <本仓库地址>
cd moviepilot-backup-web-v9
```

2. 修改 `docker-compose.yml`：将你宿主机上需要挂载的目录以 `volumes` 映射到容器（示例）：
```yaml
services:
  backup-web:
    volumes:
      - ./data:/app/data:rw          # 容器内部持久化目录（包含 backup_log.txt）
      - /vol2/1000/Video/115:/115:rw # 将宿主 /vol2/1000/Video/115 映射到容器 /115（会出现在 UI 挂载点列表）
      - /vol2/1000/Video/Video:/Video:rw
```
> 注意：**不要固定某一名称**，你可以映射任意宿主路径到容器内的任意挂载点。UI 会列出容器内可见的挂载点供选择源/目标目录。

3. 启动服务：
```bash
docker compose up -d --build
```
4. 访问：`http://<服务器IP>:18008/`（若需要可在 `docker-compose.yml` 与 `Dockerfile` 中修改 `APP_PORT` 环境变量到你希望的端口）。

## 使用建议与常见问题
- 权限：确保容器运行用户对宿主映射目录有读写权限。默认 Compose 使用 `user: "1000:1001"`，你可以修改或在宿主机上调整目录所属：`sudo chown -R 1000:1001 /path/to/dir`。
- 如果 UI 无法列出某目录，通常是因为该目录没有映射到容器，或权限不足，请检查 `docker-compose.yml` 的 `volumes` 设置并重启容器。
- **执行任务后如果看不到子目录**：本版已改进动态挂载检测与目录读取策略，通常能避免必须重启容器的问题；若仍发生，请把容器日志中相关 WARN/ERROR 打包发来以便诊断。
- `BACKUP_RATE`：降低该值可以降低瞬时 IO 压力（例如设为 `5`）。
- 日志文件：容器内 `/app/data/backup_log.txt` 用于增量备份跳过已生成项；全量模式会忽略该日志并覆盖占位文件。

## 关于 GitHub 默认的开源说明（LICENSE / About）
- GitHub 会在你创建仓库时自动生成一些描述或 LICENSE 文件（例如 MIT、Apache 等）。**保留这些默认开源说明是完全可以的，也不会影响本项目的功能**。如果你希望保留原作者的 LICENSE 或 GitHub 自动生成的许可说明，可以直接在仓库中保留相关文件（例如 `LICENSE`、`.github/` 目录等）。
- 简单来说：**不删除默认开源说明没有副作用**，只会影响许可声明，方便使用者知晓项目的授权方式。

## 版本与依赖
- Python 3.11（镜像使用 `python:3.11-slim`）
- Flask==2.2.5
- gunicorn==20.1.0

## 打包与 CI（GitHub Actions）
- 仓库包含 `.github/workflows/docker-image.yml`，用于构建并推送镜像到 GHCR。请在仓库 Secrets 中配置所需的凭证（默认使用 `secrets.GITHUB_TOKEN` 对 ghcr 做登录权限）。
- 如果你不希望自动推送，请禁用或删除该 Workflow；保留则会在每次 push 到 `main` 时构建镜像并推送（前提为你有合适的权限）。

---
感谢你和我一起基于原作者项目做的扩展。如果这确实是“最后一版”，我会把 v9 打包好并提供下载链接；若还需微调（例如配色、端口、或把 `user:` 改为 root 以避免权限问题），告诉我我会直接在包内修改并重新打包。
