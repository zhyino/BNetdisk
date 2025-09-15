import os
from pathlib import Path
import queue
import json
import re
from flask import Flask, render_template, request, jsonify, Response
from .backup import BackupWorker

# Config
APP_PORT = int(os.environ.get('APP_PORT', '18008'))
BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', '/app/data')).resolve()
ALLOWED_ROOTS_ENV = os.environ.get('ALLOWED_ROOTS', '')

# ensure backup dir exists
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_LOG = BACKUP_DIR.joinpath('backup_log.txt')
if not BACKUP_LOG.exists():
    try:
        BACKUP_LOG.touch(exist_ok=True)
    except Exception:
        pass

app = Flask(__name__, template_folder='templates', static_folder='static')

# discover mount points if ALLOWED_ROOTS not explicitly provided
def _discover_mount_points():
    roots = set()
    # always include backup dir
    roots.add(str(BACKUP_DIR))
    try:
        with open('/proc/mounts', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    fst = parts[2] if len(parts) > 2 else ''
                    # ignore pseudo filesystems
                    if fst in ('proc','sysfs','tmpfs','devtmpfs','cgroup','cgroup2','overlay','squashfs','debugfs','tracefs','securityfs','ramfs','rootfs','fusectl','mqueue'):
                        continue
                    # ignore empty or non-absolute
                    if not mp or not mp.startswith('/'):
                        continue
                    roots.add(mp)
    except Exception:
        # fallback: include common mount roots
        for p in ('/mnt', '/media', '/data', '/srv'):
            if Path(p).exists():
                roots.add(p)
    # filter out duplicates and system dirs that are too generic
    filtered = []
    for r in sorted(roots):
        if r in ('/','/proc','/sys','/dev'):
            continue
        filtered.append(r)
    return filtered

if ALLOWED_ROOTS_ENV:
    ALLOWED_ROOTS = [Path(p).resolve() for p in re.split(r'\s*,\s*', ALLOWED_ROOTS_ENV) if p]
else:
    ALLOWED_ROOTS = [Path(p) for p in _discover_mount_points()]

task_queue = queue.Queue()
worker = BackupWorker(task_queue, BACKUP_LOG, ALLOWED_ROOTS)
worker.start()

def _is_allowed_path(p: Path) -> bool:
    try:
        p = p.resolve()
    except Exception:
        return False
    for root in ALLOWED_ROOTS:
        try:
            if p == root or p.is_relative_to(root):
                return True
        except Exception:
            if str(p).startswith(str(root)):
                return True
    return False

@app.route('/')
def index():
    roots = [str(p) for p in ALLOWED_ROOTS]
    return render_template('index.html', roots=roots, app_port=APP_PORT)

@app.route('/api/roots')
def api_roots():
    return jsonify({'roots': [str(p) for p in ALLOWED_ROOTS]})

@app.route('/api/listdir')
def listdir():
    path = request.args.get('path', None)
    if not path:
        return jsonify({'error': 'missing path'}), 400
    p = Path(path)
    if not _is_allowed_path(p):
        return jsonify({'error': 'path not allowed'}), 400
    if not p.exists() or not p.is_dir():
        return jsonify({'error': 'not exists or not dir'}), 400
    entries = []
    try:
        with os.scandir(p) as it:
            for entry in it:
                entries.append({
                    'name': entry.name,
                    'path': str(Path(p) / entry.name),
                    'is_dir': entry.is_dir()
                })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
    return jsonify({'path': str(p), 'entries': entries})

@app.route('/api/add', methods=['POST'])
def api_add():
    payload = request.get_json(force=True) or {}
    tasks = payload.get('tasks') or []
    # filters: images & nfo filtered by default
    filter_images = True
    filter_nfo = True
    added = 0
    for t in tasks:
        src = Path(t.get('src', '')).resolve()
        dst = Path(t.get('dst', '')).resolve()
        if not _is_allowed_path(src) or not _is_allowed_path(dst):
            continue
        if not src.exists() or not src.is_dir():
            continue
        try:
            dst.mkdir(parents=True, exist_ok=True)
        except Exception:
            continue
        worker.add_task(src, dst, filter_images=filter_images, filter_nfo=filter_nfo)
        added += 1
    return jsonify({'added': added})

@app.route('/api/queue')
def api_queue():
    q = task_queue
    items = []
    with q.mutex:
        for item in list(q.queue):
            items.append(item)
    return jsonify({'queue': items})

@app.route('/stream')
def stream():
    def gen(q):
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        finally:
            try:
                worker.unregister_client(q)
            except Exception:
                pass
    client_q = worker.register_client()
    return Response(gen(client_q), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=APP_PORT, threaded=True)
