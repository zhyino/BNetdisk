from pathlib import Path
import os, threading, queue, time, sqlite3, io
from collections import deque

def discover_mount_points():
    roots = set()
    try:
        with open('/proc/mounts', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    fst = parts[2] if len(parts) > 2 else ''
                    if fst in ('proc','sysfs','tmpfs','devtmpfs','cgroup','cgroup2','overlay','squashfs','debugfs','tracefs','securityfs','ramfs','rootfs','fusectl','mqueue'):
                        continue
                    if not mp or not mp.startswith('/'):
                        continue
                    roots.add(mp)
    except Exception:
        for p in ('/mnt', '/media', '/data', '/srv'):
            if Path(p).exists():
                roots.add(p)
    filtered = []
    for r in sorted(roots):
        if r in ('/','/proc','/sys','/dev'):
            continue
        filtered.append(Path(r))
    return filtered

class ServiceLogWriter(threading.Thread):
    def __init__(self, path: Path, max_lines_keep=5000):
        super().__init__(daemon=True)
        self.path = Path(path)
        self.queue = queue.Queue(maxsize=10000)
        self.max_lines_keep = max_lines_keep
        self.deque = deque(maxlen=max_lines_keep)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._stop = threading.Event()

    def run(self):
        buf = []
        last_flush = time.time()
        while not self._stop.is_set():
            try:
                item = self.queue.get(timeout=1)
                buf.append(item)
                self.deque.append(item)
            except queue.Empty:
                item = None
            # flush conditions
            if buf and (len(buf) >= 50 or (time.time() - last_flush) > 1):
                try:
                    with open(self.path, 'a', encoding='utf-8') as f:
                        f.write('\n'.join(buf) + '\n')
                except Exception:
                    pass
                buf = []
                last_flush = time.time()
        # final flush
        if buf:
            try:
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(buf) + '\n')
            except Exception:
                pass

    def stop(self):
        self._stop.set()

    def append(self, line: str):
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            # drop if queue full
            pass

    def tail_lines(self, n=200):
        return list(self.deque)[-n:]

class BackupIndex:
    def __init__(self, dbpath: Path):
        self.dbpath = Path(dbpath)
        self._lock = threading.RLock()
        self._conn = None
        self._ensure()

    def _ensure(self):
        self.dbpath.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.dbpath), timeout=30, check_same_thread=False)
        cur = self._conn.cursor()
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.execute('PRAGMA synchronous=NORMAL;')
        cur.execute('CREATE TABLE IF NOT EXISTS paths(path TEXT PRIMARY KEY)')
        self._conn.commit()

    def insert_many(self, paths):
        if not paths:
            return
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.executemany('INSERT OR IGNORE INTO paths(path) VALUES(?)', ((p,) for p in paths))
                self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass

    def contains(self, path):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute('SELECT 1 FROM paths WHERE path=? LIMIT 1', (path,))
            return cur.fetchone() is not None

class BackupWorker(threading.Thread):
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.heic', '.ico'}

    def __init__(self, task_queue: queue.Queue, backup_log_path: Path, index_db: Path, allowed_roots, ops_per_sec: float = 20.0, service_log_path: Path=None):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.backup_log_path = Path(backup_log_path)
        self.allowed_roots = [p.resolve() for p in allowed_roots]
        self._clients = []
        self._clients_lock = threading.RLock()
        self._index = BackupIndex(index_db)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._pending_index = []
        self._pending_index_lock = threading.RLock()

        try:
            self.ops_per_sec = float(os.environ.get('BACKUP_RATE', str(ops_per_sec)))
        except Exception:
            self.ops_per_sec = ops_per_sec
        self._delay = 0.0 if self.ops_per_sec <= 0 else max(0.0, 1.0 / float(self.ops_per_sec))

        if service_log_path is None:
            service_log_path = self.backup_log_path.parent.joinpath('service_log.txt')
        self.service_writer = ServiceLogWriter(service_log_path)
        self.service_writer.start()

    def stop(self):
        self._stop_event.set()
        try:
            self.service_writer.stop()
        except Exception:
            pass

    def broadcast(self, msg: str):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} {msg}"
        # push to in-memory deque and file writer
        try:
            self.service_writer.append(line)
        except Exception:
            pass
        with self._clients_lock:
            for q in list(self._clients):
                try:
                    q.put_nowait(line)
                except queue.Full:
                    pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def register_client(self):
        q = queue.Queue(maxsize=1000)
        with self._clients_lock:
            self._clients.append(q)
        try:
            q.put_nowait(f"[INFO] connected")
            # send recent lines
            for l in self.service_writer.tail_lines(200):
                try:
                    q.put_nowait(l)
                except queue.Full:
                    break
        except queue.Full:
            pass
        return q

    def unregister_client(self, q):
        with self._clients_lock:
            try:
                self._clients.remove(q)
            except Exception:
                pass

    def _is_allowed_path(self, p: Path) -> bool:
        try:
            p = p.resolve()
        except Exception:
            return False
        roots = list(self.allowed_roots) + discover_mount_points()
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

    def _is_filtered(self, filename: str, filter_images: bool, filter_nfo: bool) -> bool:
        ext = Path(filename).suffix.lower()
        if filter_images and ext in self.IMAGE_EXTS:
            return True
        if filter_nfo and ext == '.nfo':
            return True
        return False

    def _create_placeholder(self, dest_file: Path, overwrite: bool = False) -> bool:
        try:
            if dest_file.exists() and not overwrite:
                return True
        except Exception:
            pass
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.broadcast(f"[ERROR] Cannot create parent directories for {dest_file}: {e}")
            return False
        tmp = dest_file.parent.joinpath(dest_file.name + '.tmp')
        try:
            with tmp.open('wb') as f:
                f.write(b'\0' * 1024)
            os.replace(str(tmp), str(dest_file))
            return True
        except Exception as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            self.broadcast(f"[ERROR] Failed to create placeholder {dest_file}: {e}")
            return False

    def _flush_index(self):
        with self._pending_index_lock:
            if not self._pending_index:
                return
            to_write = list(self._pending_index)
            self._pending_index.clear()
        try:
            self._index.insert_many(to_write)
        except Exception as e:
            self.broadcast(f"[WARN] index flush failed: {e}")

    def add_task(self, src: Path, dst: Path, filter_images: bool = True, filter_nfo: bool = True, mirror: bool = True, mode: str = 'incremental'):
        self.task_queue.put({
            'src': str(src),
            'dst': str(dst),
            'filter_images': bool(filter_images),
            'filter_nfo': bool(filter_nfo),
            'mirror': bool(mirror),
            'mode': str(mode)
        })
        self.broadcast(f"[QUEUE] Added task: {src} -> {dst} (mirror={mirror}, mode={mode})")

    def run(self):
        self.broadcast("[INFO] Worker started")
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                # periodic flush
                self._flush_index()
                continue

            src = Path(task.get('src'))
            dst = Path(task.get('dst'))
            filter_images = task.get('filter_images', True)
            filter_nfo = task.get('filter_nfo', True)
            mirror = task.get('mirror', True)
            mode = task.get('mode', 'incremental')

            self.broadcast(f"[START] {src} -> {dst} (filter_images={filter_images}, filter_nfo={filter_nfo}, mirror={mirror}, mode={mode})")

            if not self._is_allowed_path(src):
                self.broadcast(f"[WARN] Source not allowed: {src}")
                self.task_queue.task_done()
                continue
            if not self._is_allowed_path(dst):
                self.broadcast(f"[WARN] Destination not allowed: {dst}")
                self.task_queue.task_done()
                continue
            if not src.exists() or not src.is_dir():
                self.broadcast(f"[WARN] Source missing or not a directory: {src}")
                self.task_queue.task_done()
                continue

            try:
                dst.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.broadcast(f"[WARN] Cannot create destination {dst}: {e}")
                self.task_queue.task_done()
                continue

            try:
                src_name = src.resolve().name
            except Exception:
                src_name = src.name
            try:
                dst_name = dst.resolve().name
            except Exception:
                dst_name = dst.name

            if mirror and dst_name != src_name:
                dest_root = dst / src_name
            else:
                dest_root = dst

            try:
                if dest_root.resolve() == src.resolve() or dest_root.resolve().is_relative_to(src.resolve()):
                    self.broadcast(f"[WARN] Computed destination would be same as or inside source, skipping: {dest_root}")
                    self.task_queue.task_done()
                    continue
            except Exception:
                self.broadcast(f"[WARN] Could not resolve paths safely for {src} -> {dest_root}, skipping")
                self.task_queue.task_done()
                continue

            backed = 0
            skipped = 0
            to_index = []

            overwrite = (mode == 'full')
            for dirpath, dirnames, filenames in os.walk(src):
                rel = os.path.relpath(dirpath, src)
                rel = '' if rel == '.' else rel
                for fname in filenames:
                    try:
                        if self._is_filtered(fname, filter_images, filter_nfo):
                            skipped += 1
                            continue
                        src_file = Path(dirpath) / fname
                        try:
                            src_key = str(src_file.resolve())
                        except Exception:
                            src_key = str(src_file)
                        # use sqlite index to check duplicates
                        if not overwrite and self._index.contains(src_key):
                            skipped += 1
                            continue
                        target_dir = dest_root / rel
                        target_file = target_dir / fname
                        ok = self._create_placeholder(target_file, overwrite=overwrite)
                        if ok:
                            to_index.append(src_key)
                            backed += 1
                            self.broadcast(f"[OK] {src_file} -> {target_file}")
                        else:
                            skipped += 1
                    except Exception as e:
                        self.broadcast(f"[ERROR] processing file {fname}: {e}")
                    if self._delay > 0:
                        time.sleep(self._delay)
                # optional: flush index per directory to avoid huge memory
                if len(to_index) >= 200:
                    with self._pending_index_lock:
                        self._pending_index.extend(to_index)
                    to_index = []
                    self._flush_index()

            # final flush for this task
            if to_index:
                with self._pending_index_lock:
                    self._pending_index.extend(to_index)
            self._flush_index()

            self.broadcast(f"[DONE] {src} -> {dest_root} (backed={backed}, skipped={skipped})")
            self.task_queue.task_done()
