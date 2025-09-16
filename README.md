# 假文件入库管理面板

> 本项目基于并修改自 [cnlaok/BNetdisk.py](https://github.com/cnlaok/BNetdisk.py)，提供一个 Web 面板来批量生成“假文件”，用于 Plex 等媒体服务器的快速入库。

---

## 项目简介

在使用网盘 / 远程存储时，直接让 Plex 扫描网盘挂载短时间内会造成大量带宽占用。  
本项目通过生成与真实媒体同名的 **假占位文件**，让 Plex 能够在短时间内完成媒体库的扫描和入库。  
完成入库后，再将真实媒体目录映射到 Plex 容器内 **相同的路径**，即可正常播放。

✅ **优点**  
- 快速完成 Plex 入库（几百TB  几个小时就能完成）。  
- 降低短时间带宽压力。  

⚠️ **缺点**  
- 入库阶段 Plex 无法播放文件（因为是假文件）。  
- 必须在入库完成后，把真实文件映射到与假文件一致的容器路径。
- PLex暂时无法显示媒体信息   

---

## 使用步骤（Plex 配置重点）

1. **第一阶段：假文件入库**  
   - 使用本工具生成假文件，并将目标目录映射到 Plex 容器。  
   - Plex 会扫描并入库这些假文件。  

2. **第二阶段：切换真实文件**  
   - 入库完成后，将 Plex 容器中的映射切换为真实媒体文件目录。  
   - 注意：**映射路径必须和假文件路径一致**，否则 Plex 无法识别为同一条目。  

### 示例

假设要把真实文件 `/vol1/1000/CloudNAS/CloudDrive/115open，下的 影音库文件夹` 入库到 Plex：

- **假文件生成阶段**  
  在 `docker-compose.yml` 中挂载：
   ```yaml 
  - /vol1/1000/CloudNAS/CloudDrive/115ope:/CloudDrive  #源路径
  - /vol1/1000/Docker/backup-web/115:/115 #目标路径
  ```
  工具会在 `/vol1/1000/Docker/backup-web/115下生成假文件  目录为/vol1/1000/Docker/backup-web/115/CloudDrive/影音库...` 。  
  Plex 挂载：
  ```yaml
  - /vol1/1000/Docker/backup-web/115/CloudDrive:/115
  ```

- **真实文件切换阶段**  
  假文件入库完成后，把 Plex 的挂载切换到真实路径：  
  ```yaml
  - /vol1/1000/CloudNAS/CloudDrive/115open:/115
  ```
  （一定要保持映射到PLex容器中的路径不变，比如都映射到/115）  

这样 Plex 能够无缝识别条目并正常播放。

---

## 功能特性

- Web 面板操作（中文界面）：
  - 浏览容器映射的目录，选择源目录与目标目录。
  - 支持多条目录 **按索引配对** 添加任务。
  - 提供 **增量备份**（仅生成新增文件）和 **全量备份**（全部覆盖生成）。
- 占位文件生成：
  - 默认大小 1 KB（可修改为 0 字节）。  
  - 原子写入，避免并发覆盖。  
- 文件过滤：
  - 自动跳过常见图片格式（jpg/png/webp 等）。  
  - 自动跳过 `.nfo` 文件。  
。  
- IO 控制：
  - 通过 `BACKUP_RATE` 环境变量限制每秒生成文件数量，降低远程挂载压力。  

---

## 快速开始

### 1. 修改 `docker-compose.yml`
在 `volumes` 中添加你希望在 Web 页面中浏览/操作的宿主目录，例如：
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
      - ./data:/app/data:rw # 容器用于存放 backup_log.txt 与其他数据的持久化目录（容器会创建）
      # 要让 Web 页面能浏览并选择宿主机上的目录，必须在下面把宿主机目录映射到容器中（示例）：
      - ./115:/115:rw   #目标路径
      - /vol1/1000/CloudNAS/CloudDrive/115open:/Nas:rw  #源路径
      # 注意：不要映射敏感系统目录，确保容器用户对映射目录有读写权限。
    environment:
      - BACKUP_DIR=/app/data
      - BACKUP_RATE=500   #控制每秒生成速度
      - APP_PORT=18008
      # 若希望容器在运行时把 /app/data 的属主更改为宿主 UID/GID，请设置下方（可选）
      - UID=1000
      - GID=1001
    restart: unless-stopped
    # 若需要容器进程以特定 UID:GID 运行，请使用下面的 user 字段（示例）
    # user: "1000:1001"
```

### 2. 访问 Web 面板
浏览器打开：  
```
http://<服务器IP>:18008/
```

在左侧选择源目录、目标目录，点击“添加任务”即可生成假文件。

---

## 环境变量

- `APP_PORT`：Web 服务端口（默认 `18008`）  
- `BACKUP_RATE`：速率限制（每秒生成文件数，默认 `20`）  
- `UID` / `GID`：容器内运行用户（可选，避免 root 权限）  

---

## 注意事项

- 真实媒体路径与假文件路径必须在 Plex 容器中一致。  
- 建议逐步调整 `BACKUP_RATE`，避免对远程挂载产生过大 IO 压力。  
- 假文件仅用于入库，入库完成后请务必替换为真实媒体文件。  

---

## 致谢

- 原始项目：[cnlaok/BNetdisk.py](https://github.com/cnlaok/BNetdisk.py)  
- 本项目在其基础上增加了 Web 面板、日志优化、过滤规则和容器化部署支持。
