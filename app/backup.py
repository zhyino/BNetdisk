
from pathlib import Path
import os, threading, queue, time, sqlite3
from collections import deque

def discover_mount_points():
    roots = set()
    try:
        with open('/proc/mounts','r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    fst = parts[2] if len(parts)>2 else ''
                    if fst in ('proc','sysfs','tmpfs','devtmpfs','cgroup','cgroup2','overlay','squashfs','debugfs','tracefs','securityfs','ramfs','rootfs','fusectl','mqueue'):
                        continue
                    if not mp or not mp.startswith('/'):
                        continue
                    roots.add(mp)
    except Exception:
        for p in ('/mnt','/media','/data','/srv'):
            if Path(p).exists():
                roots.add(p)
    filtered = [Path(r) for r in sorted(roots) if r not in ('/','/proc','/sys','/dev')]
    return filtered

class ServiceLogWriter(threading.Thread):
    def __init__(self, path: Path, max_lines=5000):
        super().__init__(daemon=True)
        self.path = Path(path)
        self.queue = queue.Queue(maxsize=20000)
        self.deque = deque(maxlen=max_lines)
        self._stop = threading.Event()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def run(self):
        buf = []
        last = time.time()
        while not self._stop.is_set():
            try:
                line = self.queue.get(timeout=1)
                buf.append(line)
                self.deque.append(line)
            except queue.Empty:
                line = None
            if buf and (len(buf) >= 100 or (time.time()-last) > 1):
                try:
                    with open(self.path, 'a', encoding='utf-8') as f:
                        f.write('\\n'.join(buf) + '\\n')
                except Exception:
                    pass
                buf = []
                last = time.time()
        # final flush
        if buf:
            try:
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write('\\n'.join(buf) + '\\n')
            except Exception:
                pass

    def append(self, line: str):
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            # drop
            pass

    def tail(self, n=100):
        return list(self.deque)[-n:]

    def stop(self):
        self._stop.set()

class BackupIndexSQLite:
    def __init__(self, dbpath: Path):
        self.dbpath = Path(dbpath)
        self.dbpath.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.dbpath), check_same_thread=False, timeout=30)
        cur = self.conn.cursor()
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.execute('PRAGMA synchronous=NORMAL;')
        cur.execute('CREATE TABLE IF NOT EXISTS paths(path TEXT PRIMARY KEY)')
        self.conn.commit()
        self.lock = threading.RLock()

    def insert_many(self, paths):
        if not paths:
            return
        with self.lock:
            cur = self.conn.cursor()
            try:
                cur.executemany('INSERT OR IGNORE INTO paths(path) VALUES(?)', ((p,) for p in paths))
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

    def contains_many(self, paths):
        # returns a set of paths that exist in DB
        res = set()
        if not paths:
            return res
        with self.lock:
            cur = self.conn.cursor()
            CHUNK = 500
            for i in range(0, len(paths), CHUNK):
                chunk = paths[i:i+CHUNK]
                q = 'SELECT path FROM paths WHERE path IN ({})'.format(','.join('?'*len(chunk)))
                try:
                    cur.execute(q, chunk)
                    for row in cur.fetchall():
                        res.add(row[0])
                except Exception:
                    pass
        return res

class BackupWorker(threading.Thread):
    IMAGE_EXTS = {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.tiff','.svg','.heic','.ico'}
    def __init__(self, task_queue, backup_log: Path, index_db: Path, allowed_roots, ops_per_sec=20.0, service_log: Path=None, index_mode='memory'):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.backup_log = Path(backup_log)
        self.allowed_roots = [Path(p).resolve() for p in allowed_roots]
        self.ops_per_sec = float(os.environ.get('BACKUP_RATE', ops_per_sec))
        self._delay = 0.0 if self.ops_per_sec <=0 else max(0.0, 1.0/self.ops_per_sec)
        self.stop_event = threading.Event()
        self.clients = []
        self.clients_lock = threading.RLock()

        if service_log is None:
            service_log = self.backup_log.parent.joinpath('service_log.txt')
        self.service_writer = ServiceLogWriter(service_log, max_lines=5000)
        self.service_writer.start()

        self.index_mode = (os.environ.get('INDEX_MODE') or index_mode).lower()
        # memory index
        self.mem_index = set()
        self.mem_lock = threading.RLock()
        self.pending_append = []
        self.pending_lock = threading.RLock()

        # sqlite index if needed
        self.sqlite_index = None
        if self.index_mode == 'sqlite':
            self.sqlite_index = BackupIndexSQLite(index_db)

        # load existing backup_log into mem_index if memory mode
        if self.index_mode == 'memory':
            try:
                if self.backup_log.exists():
                    with open(self.backup_log, 'r', encoding='utf-8', errors='ignore') as f:
                        for ln in f:
                            p = ln.strip()
                            if p:
                                self.mem_index.add(p)
            except Exception as e:
                self.broadcast(f"[WARN] failed to load backup_log into memory: {e}")

    def broadcast(self, msg):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} {msg}"
        try:
            self.service_writer.append(line)
        except Exception:
            pass
        with self.clients_lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(line)
                except Exception:
                    pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def register_client(self):
        q = queue.Queue(maxsize=1000)
        with self.clients_lock:
            self.clients.append(q)
        # send recent 100 lines
        for l in self.service_writer.tail(100):
            try:
                q.put_nowait(l)
            except Exception:
                pass
        return q

    def unregister_client(self, q):
        with self.clients_lock:
            try:
                self.clients.remove(q)
            except Exception:
                pass

    def _is_allowed(self, p: Path):
        try:
            rp = p.resolve()
        except Exception:
            return False
        roots = list(self.allowed_roots) + discover_mount_points()
        pstr = str(rp)
        for r in roots:
            try:
                rr = Path(r).resolve()
            except Exception:
                rr = Path(r)
            try:
                if rp == rr or rp.is_relative_to(rr):
                    return True
            except Exception:
                if pstr.startswith(str(rr)):
                    return True
        return False

    def _is_filtered(self, fname, filter_images=True, filter_nfo=True):
        ext = Path(fname).suffix.lower()
        if filter_images and ext in self.IMAGE_EXTS:
            return True
        if filter_nfo and ext == '.nfo':
            return True
        return False

    def _create_placeholder(self, dest: Path, overwrite=False):
        try:
            if dest.exists() and not overwrite:
                return True
        except Exception:
            pass
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.broadcast(f"[ERROR] mkdir failed {dest.parent}: {e}")
            return False
        tmp = dest.with_suffix(dest.suffix + '.tmp')  # safer tmp in same dir
        try:
            with open(tmp, 'wb') as f:
                f.write(b'\\0'*1024)
            os.replace(str(tmp), str(dest))
            return True
        except Exception as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            self.broadcast(f"[ERROR] write placeholder failed {dest}: {e}")
            return False

    def _append_index(self, paths):
        # append new paths to mem_index and schedule persistence
        if not paths:
            return
        with self.mem_lock:
            for p in paths:
                self.mem_index.add(p)
        with self.pending_lock:
            self.pending_append.extend(paths)

    def _flush_pending(self):
        # flush pending appends to backup_log (append) and sqlite if used
        with self.pending_lock:
            to_write = list(self.pending_append)
            self.pending_append.clear()
        if not to_write:
            return
        # append to backup_log
        try:
            with open(self.backup_log, 'a', encoding='utf-8') as f:
                for p in to_write:
                    f.write(p + '\\n')
        except Exception:
            pass
        # sqlite
        if self.sqlite_index is not None:
            try:
                self.sqlite_index.insert_many(to_write)
            except Exception:
                pass

    def add_task(self, src, dst, filter_images=True, filter_nfo=True, mirror=True, mode='incremental'):
        self.task_queue.put({'src': str(src), 'dst': str(dst), 'filter_images': bool(filter_images), 'filter_nfo': bool(filter_nfo), 'mirror': bool(mirror), 'mode': mode})
        self.broadcast(f"[QUEUE] {src} -> {dst} (mode={mode})")


    def run(self):
        self.broadcast("[INFO] worker started")
        while not self.stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except Exception:
                # flush periodic
                self._flush_pending()
                continue
            src = Path(task.get('src'))
            dst = Path(task.get('dst'))
            filter_images = task.get('filter_images', True)
            filter_nfo = task.get('filter_nfo', True)
            mirror = task.get('mirror', True)
            mode = task.get('mode', 'incremental')
            overwrite = (mode == 'full')

            self.broadcast(f"[START] {src} -> {dst} (mode={mode})")

            if not self._is_allowed(src):
                self.broadcast(f"[WARN] source not allowed {src}")
                self.task_queue.task_done()
                continue
            if not self._is_allowed(dst):
                self.broadcast(f"[WARN] dst not allowed {dst}")
                self.task_queue.task_done()
                continue
            if not src.exists() or not src.is_dir():
                self.broadcast(f"[WARN] source missing {src}")
                self.task_queue.task_done()
                continue
            try:
                dst.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.broadcast(f"[WARN] cannot create dst {dst}: {e}")
                self.task_queue.task_done()
                continue

            # decide root dest path
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
                    self.broadcast(f"[WARN] destination would be inside source {dest_root}")
                    self.task_queue.task_done()
                    continue
            except Exception:
                pass

            backed = 0
            skipped = 0

            # walk src and process per-directory to batch index checks
            for dirpath, dirnames, filenames in os.walk(src):
                rel = os.path.relpath(dirpath, src)
                rel = '' if rel == '.' else rel
                # build absolute source file paths
                src_paths = [str(Path(dirpath) / fn) for fn in filenames if not self._is_filtered(fn, filter_images, filter_nfo)]
                if not src_paths:
                    continue
                # check existing via mem_index or sqlite batch
                existing = set()
                if not overwrite:
                    if self.index_mode == 'memory':
                        with self.mem_lock:
                            for p in src_paths:
                                if p in self.mem_index:
                                    existing.add(p)
                    elif self.index_mode == 'sqlite' and self.sqlite_index is not None:
                        existing = self.sqlite_index.contains_many(src_paths)
                # process files
                to_index = []
                for p in src_paths:
                    if p in existing:
                        skipped += 1
                        continue
                    # compute destination
                    fname = os.path.basename(p)
                    target_dir = dest_root / rel
                    target_file = target_dir / fname
                    ok = self._create_placeholder(target_file, overwrite=overwrite)
                    if ok:
                        backed += 1
                        to_index.append(p)
                        self.broadcast(f"[OK] {p} -> {target_file}")
                    else:
                        skipped += 1
                    if self._delay > 0:
                        time.sleep(self._delay)
                if to_index:
                    self._append_index(to_index)
                # periodically flush pending to disk/db to avoid big memory
                if len(self.pending_append) >= 1000:
                    self._flush_pending()
            # final flush per task
            self._flush_pending()
            self.broadcast(f"[DONE] {src} -> {dest_root} (backed={backed}, skipped={skipped})")
            self.task_queue.task_done()
