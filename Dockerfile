FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY backup_log.txt .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "app.app:app", "--workers", "1", "--threads", "4", "--timeout", "120"]
