FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 赋予执行权限
RUN chmod +x docker-entrypoint.sh

# 暴露端口
EXPOSE 18008

# 启动命令
ENTRYPOINT ["./docker-entrypoint.sh"]
