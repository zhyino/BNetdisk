\
        FROM python:3.11-slim
        ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
        WORKDIR /app
        COPY app/requirements.txt /app/requirements.txt
        RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
            pip install --no-cache-dir -r /app/requirements.txt && \
            apt-get remove -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
        COPY app /app
        EXPOSE 8000
        CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app", "--workers", "1", "--threads", "4", "--timeout", "120"]
