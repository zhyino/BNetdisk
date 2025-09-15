import os
from pathlib import Path
import queue
import re
import time
from flask import Flask, render_template, request, jsonify, Response
from .backup import BackupWorker, discover_mount_points

# Config
APP_PORT = int(os.environ.get('APP_PORT', '18008'))
BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', '/app/data')).resolve()
ALLOWED_ROOTS_ENV = os.environ.get('ALLOWED_ROOTS', '')

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_LOG = BACKUP_DIR.joinpath('backup_log.txt')
if not BACKUP_LOG.exists():
    try:
        BACKUP_LOG.touch(exist_ok=True)
    except Exception:
        pass

app = Flask(__name__, template_folder='templates', static_folder='static')

def _discover_mount_points_safe(limit=200):
    try:
        pts = discover_mount_points()
        return [str(p) for p in pts][:limit]
    except Exception as e:
        print(f"[WARN] discover_mount_points failed: {e}", flush=True)
        return []

if ALLOWED_ROOTS_ENV:
    ALLOWED_ROOTS = [Path(p).resolve() for p in re.split(r'\s*,\s*', ALLOWED_ROOTS_ENV) if p]
else:
    ALLOWED_ROOTS = [Path(p) for p in _discover_mount_points_safe()]

task_queue = queue.Queue()
try:
    default_rate = float(os.environ.get('BACKUP_RATE', '20'))
except Exception:
    default_rate = 20.0
worker = BackupWorker(task_queue, BACKUP_LOG, ALLOWED_ROOTS, ops_per_sec=default_rate)
worker.start()

def _is_allowed_path(p: Path) -> bool:
    try:
        p = p.resolve()
    except Exception:
        return False
    roots = [Path(r) for r in _discover_mount_points_safe()] + ALLOWED_ROOTS
    pstr = str(p)
    for root in roots:
        try:
            r = root.resolve()
        except Exception:
            r = root
        try:
            if p == r or p.is_relative_to(r):
                return True
        except Exception:
            if pstr.startswith(str(r)):
                return True
    return False

@app.route('/')
def index():
    roots = _discover_mount_points_safe()
    return render_template('index.html', roots=roots, app_port=APP_PORT)

@app.route('/api/roots')
def api_roots():
    try:
        roots = _discover_mount_points_safe()
        return jsonify({'roots': roots})
    except Exception as e:
        return jsonify({'roots': [], 'error': str(e)}), 500

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
    MAX_ENTRIES = 10000
    try:
        count = 0
        with os.scandir(p) as it:
            for entry in it:
                if count >= MAX_ENTRIES:
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except Exception:
                    is_dir = False
                entries.append({
                    'name': entry.name,
                    'path': str(Path(p) / entry.name),
                    'is_dir': is_dir
                })
                count += 1
    except Exception as e:
        try:
            for name in os.listdir(p)[:MAX_ENTRIES]:
                entry_path = p / name
                try:
                    is_dir = entry_path.is_dir()
                except Exception:
                    is_dir = False
                entries.append({
                    'name': name,
                    'path': str(entry_path),
                    'is_dir': is_dir
                })
        except Exception as e2:
            return jsonify({'error': str(e2)}), 500
    entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
    return jsonify({'path': str(p), 'entries': entries})

@app.route('/api/add', methods=['POST'])
def api_add():
    payload = request.get_json(force=True) or {}
    tasks = payload.get('tasks') or []
    filter_images = True
    filter_nfo = True
    added = 0
    skipped = []
    for t in tasks:
        try:
            src = Path(t.get('src', '')).resolve()
            dst = Path(t.get('dst', '')).resolve()
        except Exception:
            skipped.append({'task': t, 'reason': 'invalid path'})
            continue

        mode = t.get('mode', 'incremental')
        try:
            src_name = src.name
        except Exception:
            src_name = Path(t.get('src', '')).name

        mirror = True
        try:
            if dst.name == src_name:
                mirror = False
        except Exception:
            mirror = True

        potential_dst_root = dst / src_name if mirror else dst

        try:
            if str(src) == str(dst):
                skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': 'src and dst identical'})
                worker.broadcast(f"[WARN] Skipping task because src and dst are identical: {src}")
                continue
            if potential_dst_root.resolve() == src.resolve() or potential_dst_root.resolve().is_relative_to(src.resolve()):
                skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': 'destination would be inside source or identical'})
                worker.broadcast(f"[WARN] Skipping task because destination would be inside or equal to source: {potential_dst_root}")
                continue
        except Exception:
            skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': 'path resolution error'})
            worker.broadcast(f"[WARN] Path resolution error for {src} or {dst}, skipping")
            continue

        if not _is_allowed_path(src) or not _is_allowed_path(dst):
            skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': 'path not allowed'})
            worker.broadcast(f"[WARN] Skipping task due to path not allowed: {src} or {dst}")
            continue

        if not src.exists() or not src.is_dir():
            skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': 'src does not exist or not dir'})
            worker.broadcast(f"[WARN] Skipping task because src missing or not dir: {src}")
            continue

        try:
            dst.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            skipped.append({'task': {'src': str(src), 'dst': str(dst)}, 'reason': f'cannot create dst: {e}'})
            worker.broadcast(f"[WARN] Cannot create dst {dst}: {e}")
            continue

        worker.add_task(src, dst, filter_images=filter_images, filter_nfo=filter_nfo, mirror=mirror, mode=mode)
        added += 1

    return jsonify({'added': added, 'skipped': skipped})

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
