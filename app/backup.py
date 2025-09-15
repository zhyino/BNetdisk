
from pathlib import Path
import os, threading, queue, time, io

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

class BackupWorker(threading.Thread):
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.heic', '.ico'}
    MAX_SERVICE_LOG_BYTES = 1_000_000

    def __init__(self, task_queue: queue.Queue, backup_log_path: Path, allowed_roots, ops_per_sec: float = 20.0):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.backup_log_path = Path(backup_log_path)
        self.allowed_roots = [p.resolve() for p in allowed_roots]
        self._clients = []
        self._clients_lock = threading.RLock()
        self._backed_up = set()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        try:
            self.ops_per_sec = float(os.environ.get('BACKUP_RATE', str(ops_per_sec)))
        except Exception:
            self.ops_per_sec = ops_per_sec
        self._delay = 0.0 if self.ops_per_sec <= 0 else max(0.0, 1.0 / float(self.ops_per_sec))
        try:
            self.service_log = self.backup_log_path.parent.joinpath('service_log.txt')
            self.service_log.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.service_log = Path('/tmp/service_log.txt')

    def _load_backed_up_tail(self, max_lines=200000):
        if not self.backup_log_path.exists():
            return 0
        try:
            with open(self.backup_log_path, 'rb') as f:
                avg_line = 100
                to_read = max_lines * avg_line
                f.seek(0, io.SEEK_END)
                file_size = f.tell()
                start = max(0, file_size - to_read)
                f.seek(start)
                data = f.read().decode('utf-8', errors='ignore')
            lines = data.splitlines()
            tail = lines[-max_lines:]
            with self._lock:
                for line in tail:
                    line = line.strip()
                    if line:
                        self._backed_up.add(line)
            return len(tail)
        except Exception as e:
            self.broadcast(f"[WARN] Failed to load backup_log tail: {e}")
            return 0

    def _save_backed_up(self):
        temp = self.backup_log_path.with_suffix('.tmp')
        try:
            with temp.open('w', encoding='utf-8') as f:
                for p in sorted(self._backed_up):
                    f.write(p + "\\n")
            os.replace(str(temp), str(self.backup_log_path))
        except Exception as e:
            self._append_service_log(f"[ERROR] Failed to persist backup log: {e}")

    def register_client(self):
        q = queue.Queue(maxsize=1000)
        with self._clients_lock:
            self._clients.append(q)
        try:
            q.put_nowait(f"[INFO] connected")
        except queue.Full:
            pass
        return q

    def unregister_client(self, q):
        with self._clients_lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def _append_service_log(self, msg: str):
        try:
            with open(self.service_log, 'a', encoding='utf-8') as f:
                f.write(msg + "\\n")
        except Exception:
            pass
        # truncate/rotate to keep file bounded (best-effort)
        try:
            p = self.service_log
            if p.exists():
                size = p.stat().st_size
                if size > self.MAX_SERVICE_LOG_BYTES * 2:
                    try:
                        with open(p, 'rb') as f:
                            f.seek(-self.MAX_SERVICE_LOG_BYTES, 2)
                            tail = f.read()
                        with open(p, 'wb') as f:
                            f.write(tail)
                    except Exception:
                        pass
        except Exception:
            pass

    def broadcast(self, msg: str):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} {msg}"
        try:
            self._append_service_log(line)
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

    def stop(self):
        self._stop_event.set()

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
                f.write(b'\\0' * 1024)
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

    def run(self):
        count = self._load_backed_up_tail(max_lines=200000)
        if count:
            self.broadcast(f"[INFO] Loaded {count} entries from backup_log (tail).")
        else:
            self.broadcast(f"[INFO] No existing backup_log entries loaded or empty file.")

        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
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
                        with self._lock:
                            if not overwrite and src_key in self._backed_up:
                                skipped += 1
                                continue
                        target_dir = dest_root / rel
                        target_file = target_dir / fname
                        ok = self._create_placeholder(target_file, overwrite=overwrite)
                        if ok:
                            with self._lock:
                                self._backed_up.add(src_key)
                            backed += 1
                            self.broadcast(f"[OK] {src_file} -> {target_file}")
                        else:
                            skipped += 1
                    except Exception as e:
                        self.broadcast(f"[ERROR] processing file {fname}: {e}")
                    if self._delay > 0:
                        time.sleep(self._delay)

            with self._lock:
                self._save_backed_up()

            self.broadcast(f"[DONE] {src} -> {dest_root} (backed={backed}, skipped={skipped})")
            self.task_queue.task_done()
