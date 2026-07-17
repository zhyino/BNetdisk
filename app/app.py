"""Flask application factory and HTTP API for BNetdisk."""
from __future__ import annotations

import io
import os
import queue
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from . import __version__
from .config import (
    ALLOWED_ROOTS_ENV,
    APP_PORT,
    BACKUP_DIR,
    BACKUP_RATE,
    MAX_LIST_ENTRIES,
    MAX_LOG_LINES,
    SERVICE_LOG,
    SSE_KEEPALIVE_SECONDS,
    VIDEO_EXTS,
)
from .paths import (
    build_dest_final,
    discover_mount_points,
    is_allowed_path,
    list_browser_roots,
    normalize_roots,
    parse_allowed_roots_env,
    path_under_root,
)
from .worker import BackupWorker

BACKUP_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder='templates', static_folder='static')


def _discover_mount_points_safe(limit: int = 200):
    """Mount roots for the directory browser (container internals filtered out)."""
    try:
        return list_browser_roots(limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f'[WARN] list_browser_roots failed: {exc}', flush=True)
        try:
            points = discover_mount_points()
            return [str(path) for path in points if not str(path).startswith(('/app', '/usr', '/etc', '/var', '/proc', '/sys', '/dev', '/run'))][:limit]
        except Exception as exc2:  # noqa: BLE001
            print(f'[WARN] discover_mount_points failed: {exc2}', flush=True)
            return []


if ALLOWED_ROOTS_ENV:
    ALLOWED_ROOTS = parse_allowed_roots_env(ALLOWED_ROOTS_ENV)
else:
    ALLOWED_ROOTS = normalize_roots(_discover_mount_points_safe())

task_queue: queue.Queue = queue.Queue()
worker = BackupWorker(
    task_queue,
    BACKUP_DIR,
    ALLOWED_ROOTS,
    ops_per_sec=BACKUP_RATE,
    service_log_path=SERVICE_LOG,
    strict_allowed=bool(ALLOWED_ROOTS_ENV),
)
worker.start()


def _allowed(path: Path) -> bool:
    # When ALLOWED_ROOTS is explicitly configured, do not expand via live mounts.
    # That keeps sandboxing predictable and prevents accidental access outside the allow-list.
    if ALLOWED_ROOTS_ENV:
        return is_allowed_path(path, ALLOWED_ROOTS)
    return is_allowed_path(path, ALLOWED_ROOTS, normalize_roots(_discover_mount_points_safe()))


def _safe_int(value, default: int, minimum: int = 1, maximum: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def tail_file_lines(path: Path, lines: int = 100):
    lines = min(lines, MAX_LOG_LINES)
    if not path.exists():
        return []
    try:
        with open(path, 'rb') as handle:
            to_read = lines * 200
            handle.seek(0, io.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - to_read))
            data = handle.read().decode('utf-8', errors='ignore')
        return data.splitlines()[-lines:]
    except OSError:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
                return handle.readlines()[-lines:]
        except OSError:
            return []


@app.route('/')
def index():
    if ALLOWED_ROOTS_ENV and ALLOWED_ROOTS:
        roots = [str(path) for path in ALLOWED_ROOTS]
    else:
        roots = _discover_mount_points_safe()
    return render_template(
        'index.html',
        roots=roots,
        app_port=APP_PORT,
        version=__version__,
        video_exts=sorted(VIDEO_EXTS),
    )


@app.route('/api/health')
def api_health():
    status = worker.get_status()
    return jsonify({
        'ok': True,
        'version': __version__,
        'status': status,
    })


@app.route('/api/meta')
def api_meta():
    return jsonify({
        'version': __version__,
        'videos_only': True,
        'video_exts': sorted(VIDEO_EXTS),
        'backup_rate': worker.get_rate(),
        'default_backup_rate': BACKUP_RATE,
        'app_port': APP_PORT,
        'rate_min': 0,
        'rate_max': 5000,
    })


@app.route('/api/rate', methods=['GET', 'POST'])
def api_rate():
    if request.method == 'GET':
        return jsonify({
            'ops_per_sec': worker.get_rate(),
            'default_ops_per_sec': BACKUP_RATE,
            'min': 0,
            'max': 5000,
            'hint': 'Rate limits SOURCE directory scan (files/sec). Protects cloud mounts from aggressive readdir/stat. 0 = unlimited.',
        })

    payload = request.get_json(silent=True) or {}
    raw = payload.get('ops_per_sec', payload.get('rate', request.args.get('ops_per_sec')))
    if raw is None:
        return jsonify({'error': 'missing ops_per_sec', 'ops_per_sec': worker.get_rate()}), 400
    try:
        applied = worker.set_rate(raw)
    except ValueError as exc:
        return jsonify({'error': str(exc), 'ops_per_sec': worker.get_rate()}), 400
    return jsonify({
        'ok': True,
        'ops_per_sec': applied,
        'message': 'unlimited' if applied <= 0 else f'{applied:g} files/sec',
    })


@app.route('/api/roots')
def api_roots():
    try:
        if ALLOWED_ROOTS_ENV and ALLOWED_ROOTS:
            roots = [str(path) for path in ALLOWED_ROOTS]
        else:
            roots = _discover_mount_points_safe()
        return jsonify({'roots': roots, 'count': len(roots)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({'roots': [], 'count': 0, 'error': str(exc)}), 500


@app.route('/api/listdir')
def listdir():
    path = request.args.get('path')
    if not path:
        return jsonify({'error': 'missing path'}), 400

    target = Path(path)
    if not _allowed(target):
        return jsonify({'error': 'path not allowed'}), 400
    if not target.exists() or not target.is_dir():
        return jsonify({'error': 'not exists or not dir'}), 400

    entries = []
    try:
        with os.scandir(target) as iterator:
            for entry in iterator:
                if len(entries) >= MAX_LIST_ENTRIES:
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                entries.append({
                    'name': entry.name,
                    'path': str(Path(target) / entry.name),
                    'is_dir': is_dir,
                    'is_video': (not is_dir) and BackupWorker.is_video_file(entry.name),
                })
    except OSError:
        try:
            for name in os.listdir(target)[:MAX_LIST_ENTRIES]:
                entry_path = target / name
                try:
                    is_dir = entry_path.is_dir()
                except OSError:
                    is_dir = False
                entries.append({
                    'name': name,
                    'path': str(entry_path),
                    'is_dir': is_dir,
                    'is_video': (not is_dir) and BackupWorker.is_video_file(name),
                })
        except OSError as exc:
            return jsonify({'error': str(exc)}), 500

    entries.sort(key=lambda item: (not item['is_dir'], item['name'].lower()))
    return jsonify({
        'path': str(target),
        'entries': entries,
        'count': len(entries),
        'truncated': len(entries) >= MAX_LIST_ENTRIES,
    })


@app.route('/api/add', methods=['POST'])
def api_add():
    payload = request.get_json(silent=True) or {}
    tasks = payload.get('tasks') or []
    if not isinstance(tasks, list):
        return jsonify({'error': 'tasks must be a list', 'added': 0, 'skipped': []}), 400

    videos_only = bool(payload.get('videos_only', True))
    added = 0
    skipped = []

    for task in tasks:
        if not isinstance(task, dict):
            skipped.append({'task': task, 'reason': 'invalid task object'})
            continue

        try:
            src = Path(task.get('src', '')).resolve()
            dst = Path(task.get('dst', '')).resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            skipped.append({'task': task, 'reason': 'invalid path'})
            continue

        mode = task.get('mode', 'incremental')
        if mode not in ('incremental', 'full'):
            mode = 'incremental'

        dest_final = build_dest_final(src, dst)

        try:
            if src == dst:
                skipped.append({
                    'task': {'src': str(src), 'dst': str(dst)},
                    'reason': 'src and dst identical',
                })
                worker.broadcast(f'[WARN] Skipping task because src and dst are identical: {src}')
                continue
            if dest_final.resolve() == src.resolve() or path_under_root(dest_final, src):
                skipped.append({
                    'task': {'src': str(src), 'dst': str(dst)},
                    'reason': 'destination would be inside source or identical',
                })
                worker.broadcast(
                    f'[WARN] Skipping task because destination would be inside or equal to source: {dest_final}'
                )
                continue
        except (OSError, RuntimeError):
            skipped.append({
                'task': {'src': str(src), 'dst': str(dst)},
                'reason': 'path resolution error',
            })
            worker.broadcast(f'[WARN] Path resolution error for {src} or {dst}, skipping')
            continue

        if not _allowed(src) or not _allowed(dst):
            skipped.append({
                'task': {'src': str(src), 'dst': str(dst)},
                'reason': 'path not allowed',
            })
            worker.broadcast(f'[WARN] Skipping task due to path not allowed: {src} or {dst}')
            continue

        if not src.exists() or not src.is_dir():
            skipped.append({
                'task': {'src': str(src), 'dst': str(dst)},
                'reason': 'src does not exist or not dir',
            })
            worker.broadcast(f'[WARN] Skipping task because src missing or not dir: {src}')
            continue

        try:
            dest_final.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            skipped.append({
                'task': {'src': str(src), 'dst': str(dst)},
                'reason': f'cannot create dst: {exc}',
            })
            worker.broadcast(f'[WARN] Cannot create dst {dest_final}: {exc}')
            continue

        worker.add_task(
            src,
            dest_final,
            videos_only=videos_only,
            mirror=False,
            mode=mode,
        )
        added += 1

    return jsonify({
        'added': added,
        'skipped': skipped,
        'videos_only': videos_only,
    })


@app.route('/api/queue')
def api_queue():
    items = []
    with task_queue.mutex:
        for item in list(task_queue.queue):
            items.append(item)
    status = worker.get_status()
    return jsonify({
        'queue': items,
        'size': len(items),
        'current': status.get('current'),
        'last_result': status.get('last_result'),
    })


@app.route('/api/status')
def api_status():
    return jsonify(worker.get_status())


@app.route('/api/logs')
def api_logs():
    count = _safe_int(request.args.get('n', str(MAX_LOG_LINES)), MAX_LOG_LINES, 1, MAX_LOG_LINES)
    return jsonify({'lines': tail_file_lines(SERVICE_LOG, count)})


@app.route('/stream')
def stream():
    def generate(client_q: queue.Queue):
        try:
            while True:
                try:
                    msg = client_q.get(timeout=SSE_KEEPALIVE_SECONDS)
                    yield f'data: {msg}\n\n'
                except queue.Empty:
                    yield ': keepalive\n\n'
        finally:
            try:
                worker.unregister_client(client_q)
            except Exception:
                pass

    client_q = worker.register_client()
    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    }
    return Response(generate(client_q), mimetype='text/event-stream', headers=headers)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=APP_PORT, threaded=True)
