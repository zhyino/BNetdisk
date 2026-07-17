# 假文件入库管理面板

> 本项目基于并修改自 [cnlaok/BNetdisk.py](https://github.com/cnlaok/BNetdisk.py)，提供一个 Web 面板来批量生成“假文件”，用于 Plex 等媒体服务器的快速入库。

---

## 项目简介

在使用网盘 / 远程存储时，直接让 Plex 扫描网盘挂载，短时间内会造成大量带宽占用。  
本项目通过生成与真实媒体 **同名、同目录结构** 的 **1KB 假占位文件**，让 Plex 先快速完成扫库入库。  
入库完成后，再把真实媒体目录映射到 Plex 容器内 **相同的路径**，即可正常播放。

### 优点
- 扫库快，适合大体量媒体库
- 降低短时间对网盘 / 远程挂载的带宽冲击
- 切换真实文件后可继续使用已入库条目（路径保持一致时）

### 缺点 / 注意
- 入库阶段无法正常播放（内容是 1KB 假文件）
- 媒体信息、海报、时长等可能不完整或不准确
- 必须保证切换前后 Plex 容器内路径一致，否则会变成“新条目”
- **目标目录请选本地硬盘**，不要选网盘路径

当前版本：**v0.14.1**

---

## 工作原理

1. 在 Web 面板选择 **源目录**（真实视频，可来自网盘挂载）
2. 选择 **目标目录**（假文件输出位置，请选本地硬盘）
3. 工具按源目录结构，在目标下生成同名视频占位文件
4. 把生成结果挂给 Plex 扫库
5. 扫库完成后，Plex 容器内路径不变，只切换宿主机真实目录

默认路径布局示例：

```text
源目录：  /CloudDrive/影音库/电影/xxx.mkv
目标目录：/115
生成结果：/115/CloudDrive/影音库/电影/xxx.mkv
```

---

## 使用步骤（Plex 配置重点）

### 阶段一：假文件入库

1. 用本工具生成假文件到本地目标目录
2. 把“假文件对应结构”映射进 Plex
3. 让 Plex 扫描并入库

### 阶段二：切换真实文件

1. 保持 Plex 容器内路径不变
2. 只把宿主机映射从假文件目录切到真实媒体目录
3. 刷新 / 分析媒体库后即可播放

### 示例

假设真实媒体在：

```text
/vol1/1000/CloudNAS/CloudDrive/115open/影音库
```

**本工具 docker-compose 挂载示例：**

```yaml
volumes:
  - /vol1/1000/CloudNAS/CloudDrive/115open:/CloudDrive:ro  # 源：网盘
  - /vol1/1000/Docker/backup-web/115:/115:rw               # 目标：本地硬盘
```

生成结果类似：

```text
/vol1/1000/Docker/backup-web/115/CloudDrive/影音库/...
```

**Plex 假文件阶段：**

```yaml
- /vol1/1000/Docker/backup-web/115/CloudDrive:/media/library
```

**Plex 真实文件阶段（容器内路径保持不变）：**

```yaml
- /vol1/1000/CloudNAS/CloudDrive/115open:/media/library
```

关键点：Plex 容器内始终是 `/media/library`，只切换宿主机真实目录。

---

## 功能特性

### Web 面板
- 中文深色界面，源 / 目标双栏目录浏览
- 按索引横向配对任务（第 1 源 → 第 1 目标）
- 增量 / 全量模式
- 运行日志（SSE + 断线回退）
- 任务队列与当前任务状态
- 面板内可调 **源目录扫描速度**
- 详细使用说明（原理、Plex 替换路径、优缺点）

### 生成规则
- 默认 **只生成视频** 占位文件  
  支持：`mp4/mkv/avi/mov/wmv/flv/webm/m4v/mpg/mpeg/m2ts/mts/ts/vob/iso/rmvb/rm/3gp/ogv/f4v/asf/divx/xvid/tp/trp/mxf`
- 图片、字幕、`.nfo`、文本、音频等一律跳过
- 占位文件默认 1KB，原子写入

### 速率控制（保护源 / 网盘）
- 限速对象是 **源目录扫描**（每个被检查的源文件都会计入，包括被跳过的非视频）
- 目的：避免对网盘挂载频繁 `readdir/stat` 造成封控或报错
- 可在面板实时调整，也可用环境变量 `BACKUP_RATE` 设置默认值
- 建议：
  - 源在网盘：`20–100` 个/秒
  - 源在本地：可更高
  - `0` = 不限速

---

## 快速开始

### 1. 修改 `docker-compose.yml`

把你要浏览的目录映射进容器，例如：

```yaml
services:
  backup-web:
    build:
      context: .
      dockerfile: Dockerfile
    image: ghcr.io/zhyino/bnetdisk:latest
    container_name: backup-web
    ports:
      - "18008:18008"
    volumes:
      - ./data:/app/data:rw
      # 源目录（真实视频，可来自网盘）
      - /vol1/1000/CloudNAS/CloudDrive/115open:/Nas:ro
      # 目标目录（假文件输出，请用本地硬盘）
      - ./115:/115:rw
    environment:
      - BACKUP_DIR=/app/data
      - BACKUP_RATE=20          # 源目录扫描速度（个/秒），0=不限速
      - APP_PORT=18008
      # 可选：限制可访问根路径（逗号分隔）。设置后只允许这些路径
      # - ALLOWED_ROOTS=/Nas,/115,/app/data
      # 可选：数据目录属主
      # - UID=1000
      # - GID=1001
    restart: unless-stopped
```

### 2. 启动

```bash
docker compose up --build -d
```

### 3. 打开面板

```text
http://<服务器IP>:18008/
```

### 4. 操作顺序

1. 左侧选 **源目录**（真实视频）→ 添加为源目录  
2. 右侧选 **目标目录**（本地硬盘）→ 添加为目标目录  
3. 确认下方“待生成任务”配对  
4. 设置增量/全量，以及源目录扫描速度  
5. 点 **开始生成假文件**  
6. 在右侧日志查看进度  

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_PORT` | `18008` | Web 端口 |
| `BACKUP_DIR` | `/app/data` | 服务日志等数据目录 |
| `BACKUP_RATE` | `20` | 源目录扫描速度（文件/秒）。`0` 表示不限速 |
| `ALLOWED_ROOTS` | 空 | 可选，逗号分隔的允许根路径。设置后只允许这些路径，更安全 |
| `UID` / `GID` | 空 | 可选，调整 `/app/data` 属主 |

面板内也可随时修改扫描速度，无需重启容器。

---

## 本地开发运行

```bash
pip install -r requirements.txt
export BACKUP_DIR=./data
export ALLOWED_ROOTS="$(pwd)/data"
export BACKUP_RATE=20
python3 -m app.app
```

浏览器打开：http://127.0.0.1:18008

---

## 项目结构

```text
app/
  app.py              # Flask API / 页面
  worker.py           # 任务队列与占位文件生成
  paths.py            # 挂载点发现与路径安全
  config.py           # 配置与视频扩展名
  logging_service.py  # 日志写入
  templates/          # 前端页面
  static/             # CSS / JS
```

---

## 注意事项

1. **目标目录请选本地硬盘**，源目录才适合挂网盘  
2. Plex 切换真实文件时，**容器内路径必须保持一致**  
3. 源在网盘时不要把扫描速度开太高，优先 `20–100`  
4. `gunicorn` 请保持 `workers=1`（多 worker 会导致内存队列状态不共享）  
5. 不要映射敏感系统目录；确保容器对目标目录有写权限  

---

## 致谢

- 原始项目：[cnlaok/BNetdisk.py](https://github.com/cnlaok/BNetdisk.py)
- 本项目在其基础上增加了 Web 面板、仅视频生成、源扫描限速、路径安全加固与容器化部署支持
