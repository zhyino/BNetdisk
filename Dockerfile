FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
# ensure backup dir exists in image; compose may mount host folder over it
RUN mkdir -p /app/data && mkdir -p /mnt/inputs && mkdir -p /mnt/outputs

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "app.app:app", "--workers", "1", "--threads", "4", "--timeout", "120"]
