FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV APP_PORT=18008

EXPOSE 18008

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${APP_PORT} app.app:app --workers 1 --threads 4 --timeout 120"]
