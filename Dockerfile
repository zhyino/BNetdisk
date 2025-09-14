FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录并设置权限
RUN mkdir -p /app/logs && chown -R 1000:1001 /app/logs

# 运行应用
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app.app:app"]
