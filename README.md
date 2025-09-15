# BNetdisk 假文件生成工具

## 项目简介

BNetdisk是一个用于生成大规模占位文件的工具，旨在模拟真实备份环境进行系统测试和性能评估。通过生成指定结构的假文件，用户可以测试备份系统在处理数百万级文件时的表现，而无需占用大量存储空间。

该工具采用Web界面实时展示生成进度，支持任务队列管理和自动日志轮转，适合系统管理员、开发人员和测试工程师使用。

## 功能特点

- 生成指定结构的占位文件（1KB大小）
- 支持过滤图片文件和.nfo文件
- 实时日志显示（仅保留最新200行）
- 任务队列管理和监控
- 自动日志轮转，防止磁盘空间耗尽
- 支持增量备份模式
- 容器化部署，跨平台兼容
- 可处理数百万级文件生成任务

## 技术栈

- 后端：Python 3.9+, Flask, Gunicorn
- 前端：HTML, JavaScript, CSS
- 部署：Docker, Docker Compose

## 安装与部署

### 前提条件

- Docker 19.03+
- Docker Compose 1.27+

### 快速部署

1. 克隆仓库
git clone https://github.com/zhyino/BNetdisk.git
cd BNetdisk
2. 启动服务
docker-compose up -d
3. 访问Web界面

打开浏览器，访问 `http://localhost:18008`

## 使用方法

### 基本操作

服务启动后，Web界面会显示实时日志和系统状态。通过API可以添加文件生成任务。

### 添加任务API

发送POST请求到 `/api/add` 端点：
curl -X POST http://localhost:18008/api/add \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "src": "/path/to/source",
        "dst": "/path/to/destination",
        "mode": "incremental",
        "filter_images": true,
        "filter_nfo": true,
        "mirror": false
      }
    ]
  }'
参数说明：
- `src`: 源目录路径（需要存在的目录）
- `dst`: 目标目录路径（生成文件的位置）
- `mode`: 备份模式，`incremental`（增量）或`full`（全量）
- `filter_images`: 是否过滤图片文件（默认true）
- `filter_nfo`: 是否过滤.nfo文件（默认true）
- `mirror`: 是否镜像源目录结构（默认false）

### 查看任务队列
curl http://localhost:18008/api/queue
### 获取日志
curl http://localhost:18008/api/logs?n=200
## 配置选项

通过修改`docker-compose.yml`中的环境变量进行配置：

- `BACKUP_DIR`: 数据存储目录（默认`/app/data`）
- `BACKUP_RATE`: 处理速率（默认50）
- `APP_PORT`: 应用端口（默认18008）
- `GUNICORN_WORKERS`: Gunicorn工作进程数（默认2）
- `GUNICORN_THREADS`: 每个工作进程的线程数（默认4）

## 性能优化

对于需要生成数百万级文件的场景：

1. 适当提高`BACKUP_RATE`值（建议50-100）
2. 增加Docker资源限制：deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G3. 确保目标磁盘有足够的空间和IO性能

## 停止与更新
# 停止服务
docker-compose down

# 更新服务
git pull
docker-compose pull
docker-compose up -d
## 注意事项

- 确保源目录和目标目录有正确的权限
- 大规模文件生成可能需要较长时间，请耐心等待
- 日志文件自动轮转，单个文件最大500KB，保留5个备份
- 前端仅显示最新200行日志，减少浏览器资源占用