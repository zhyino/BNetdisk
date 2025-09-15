import os
from pathlib import Path
import queue
import json
from flask import Flask, render_template, request, jsonify, Response
from .backup import BackupWorker

# Config from env
BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', '/app/data')).resolve()
ALLOWED_ROOTS = os.environ.get('ALLOWED_ROOTS', '/mnt/inputs,/mnt/outputs,/app/data')
ALLOWED_ROOTS = [Path(p).resolve() for p in ALLOWED_ROOTS.split(',') if p]

# ensure backup dir exists and backup log file path
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_LOG = BACKUP_DIR.joinpath('backup_log.txt')
if not BACKUP_LOG.exists():
    try:
        BACKUP_LOG.touch(exist_ok=True)
    except Exception:
        pass

app = Flask(__name__, template_folder='templates', static_folder='static')

task_queue = queue.Queue()
worker = BackupWorker(task_queue, BACKUP_LOG, ALLOWED_ROOTS)
worker.start()

# helper to ensure path is under allowed roots
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
    # pass allowed roots for UI to render entry points
    roots = [str(p) for p in ALLOWED_ROOTS]
    return render_template('index.html', roots=roots)

@app.route('/api/listdir')
def listdir():
    path = request.args.get('path', None)
    if not path:
        # return roots
        return jsonify({'roots': [str(p) for p in ALLOWED_ROOTS]})

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
    # sort directories first then files
    entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
    return jsonify({'path': str(p), 'entries': entries})

@app.route('/api/add', methods=['POST'])
def api_add():
    data = request.get_json(force=True) or {}
    tasks = data.get('tasks') or []
    filter_images = data.get('filter_images', True)
    filter_nfo = data.get('filter_nfo', True)
    added = 0
    for t in tasks:
        src = Path(t.get('src', '')).resolve()
        dst = Path(t.get('dst', '')).resolve()
        if not _is_allowed_path(src):
            continue
        if not _is_allowed_path(dst):
            continue
        if not src.exists() or not src.is_dir():
            continue
        # ensure dst exists
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
    app.run(host='0.0.0.0', port=8000, threaded=True)
