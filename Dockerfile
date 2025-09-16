FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app /app/app
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh
RUN mkdir -p /app/data
ENV PYTHONUNBUFFERED=1
ENV APP_PORT=18008
ENV BACKUP_RATE=20
EXPOSE 18008
ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${APP_PORT} app.app:app --workers 1 --threads 4 --timeout 120"]
