import os

workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gevent'
bind = f"0.0.0.0:{os.environ.get('APP_PORT', '18008')}"
timeout = 120
keepalive = 5
