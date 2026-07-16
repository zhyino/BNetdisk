from pathlib import Path
import os
import queue
import threading
import time
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
                    if fst in (
                        'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'cgroup', 'cgroup2',
                        'overlay', 'squashfs', 'debugfs', 'tracefs', 'securityfs',
                        'ramfs', 'rootfs', 'fusectl', 'mqueue',
                    ):
                        continue
                    if not mp or not mp.startswith('/'):
                        continue
                    roots.add(mp)
    except Exception:
        for p in ('/mnt', '/media', '/data', '/srv', '/Volumes', '/Users'):
            if Path(p).exists():
                roots.add(p)

    # Always include BACKUP_DIR parent volume candidates when available.
    for p in ('/app/data', '/app'):
        if Path(p).exists():
            roots.add(p)

    filtered = []
    for r in sorted(roots):
        if r in ('/', '/proc', '/sys', '/dev'):
            continue
        filtered.append(Path(r))
    return filtered


class ServiceLogWriter(threading.Thread):
    def __init__(self, path: Path, max_lines_keep=5000):
        super().__init__(daemon=True)
        self.path = Path(path)
        self.queue = queue.Queue(maxsize=10000)
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
                if item is None:
                    # stop signal or sentinel
                    pass
                else:
                    buf.append(item)
                    self.deque.append(item)
            except queue.Empty:
                item = None
            if buf and (len(buf) >= 50 or (time.time() - last_flush) > 1 or self._stop.is_set()):
                try:
                    with open(self.path, 'a', encoding='utf-8') as f:
                        f.write('\n'.join(buf) + '\n')
                except Exception:
                    pass
                buf = []
                last_flush = time.time()
        if buf:
            try:
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(buf) + '\n')
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        # Wake the writer so remaining buffered lines can flush promptly.
        try:
            self.queue.put_nowait(None)
        except Exception:
            pass

    def append(self, line: str):
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            pass

    def tail_lines(self, n=100):
        return list(self.deque)[-n:]


class BackupWorker(threading.Thread):
    # Only these media extensions are materialized as placeholders.
    VIDEO_EXTS = {
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
        '.m4v', '.mpg', '.mpeg', '.m2ts', '.mts', '.ts', '.vob',
        '.iso', '.rmvb', '.rm', '.3gp', '.ogv', '.f4v', '.asf',
        '.divx', '.xvid', '.tp', '.trp', '.mxf',
    }
    IMAGE_EXTS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
        '.tiff', '.svg', '.heic', '.ico',
    }
    SUBTITLE_EXTS = {
        '.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx', '.sup',
        '.smi', '.sami', '.lrc', '.ttml', '.dfxp', '.mks',
    }

    def __init__(
        self,
        task_queue: queue.Queue,
        backup_dir: Path,
        allowed_roots,
        ops_per_sec: float = 20.0,
        service_log_path: Path = None,
    ):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.backup_dir = Path(backup_dir)
        self.allowed_roots = []
        for p in allowed_roots:
            try:
                self.allowed_roots.append(Path(p).resolve())
            except Exception:
                continue
        self._clients = []
        self._clients_lock = threading.RLock()
        self._stop_event = threading.Event()

        try:
            self.ops_per_sec = float(os.environ.get('BACKUP_RATE', str(ops_per_sec)))
        except Exception:
            self.ops_per_sec = ops_per_sec
        self._delay = 0.0 if self.ops_per_sec <= 0 else max(0.0, 1.0 / float(self.ops_per_sec))

        if service_log_path is None:
            service_log_path = self.backup_dir.joinpath('service_log.txt')
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
            q.put_nowait('[INFO] connected')
            for line in self.service_writer.tail_lines(100):
                try:
                    q.put_nowait(line)
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

    def _path_under_root(self, path: Path, root: Path) -> bool:
        try:
            path = path.resolve()
            root = root.resolve()
        except Exception:
            return False
        try:
            return path == root or path.is_relative_to(root)
        except AttributeError:
            path_str = str(path)
            root_str = str(root)
            return path_str == root_str or path_str.startswith(root_str.rstrip('/') + '/')
        except Exception:
            return False

    def _is_allowed_path(self, p):
        try:
            p = p.resolve()
        except Exception:
            return False
        roots = list(self.allowed_roots) + discover_mount_points()
        for root in roots:
            if self._path_under_root(p, root):
                return True
        return False

    def _is_video_file(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in self.VIDEO_EXTS

    def _is_filtered(
        self,
        filename: str,
        filter_images: bool = True,
        filter_nfo: bool = True,
        filter_subtitles: bool = True,
        videos_only: bool = True,
    ) -> bool:
        """Return True when the file should be skipped.

        Default mode is videos_only: only VIDEO_EXTS are generated.
        """
        ext = Path(filename).suffix.lower()
        if videos_only:
            return not self._is_video_file(filename)
        if filter_images and ext in self.IMAGE_EXTS:
            return True
        if filter_nfo and ext == '.nfo':
            return True
        if filter_subtitles and ext in self.SUBTITLE_EXTS:
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

        tmp = dest_file.parent.joinpath(f'.{dest_file.name}.{os.getpid()}.{threading.get_ident()}.tmp')
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

    def add_task(
        self,
        src: Path,
        dst: Path,
        filter_images: bool = True,
        filter_nfo: bool = True,
        filter_subtitles: bool = True,
        videos_only: bool = True,
        mirror: bool = True,
        mode: str = 'incremental',
    ):
        self.task_queue.put({
            'src': str(src),
            'dst': str(dst),
            'filter_images': bool(filter_images),
            'filter_nfo': bool(filter_nfo),
            'filter_subtitles': bool(filter_subtitles),
            'videos_only': bool(videos_only),
            'mirror': bool(mirror),
            'mode': str(mode),
        })
        self.broadcast(
            f"[QUEUE] Added task: {src} -> {dst} "
            f"(mirror={mirror}, mode={mode}, videos_only={videos_only})"
        )

    def run(self):
        self.broadcast('[INFO] Worker started')
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue

            src = Path(task.get('src'))
            dst = Path(task.get('dst'))
            filter_images = task.get('filter_images', True)
            filter_nfo = task.get('filter_nfo', True)
            filter_subtitles = task.get('filter_subtitles', True)
            videos_only = task.get('videos_only', True)
            mirror = task.get('mirror', True)
            mode = task.get('mode', 'incremental')

            self.broadcast(
                f"[START] {src} -> {dst} "
                f"(videos_only={videos_only}, filter_images={filter_images}, "
                f"filter_nfo={filter_nfo}, filter_subtitles={filter_subtitles}, "
                f"mirror={mirror}, mode={mode})"
            )

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
                if dest_root.resolve() == src.resolve() or self._path_under_root(dest_root, src):
                    self.broadcast(
                        f"[WARN] Computed destination would be same as or inside source, skipping: {dest_root}"
                    )
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
                if self._stop_event.is_set():
                    break
                rel = os.path.relpath(dirpath, src)
                rel = '' if rel == '.' else rel
                for fname in filenames:
                    try:
                        if self._is_filtered(
                            fname,
                            filter_images=filter_images,
                            filter_nfo=filter_nfo,
                            filter_subtitles=filter_subtitles,
                            videos_only=videos_only,
                        ):
                            skipped += 1
                            continue
                        src_file = Path(dirpath) / fname
                        target_dir = dest_root / rel
                        target_file = target_dir / fname
                        try:
                            if target_file.exists() and not overwrite:
                                skipped += 1
                                continue
                        except Exception:
                            pass
                        ok = self._create_placeholder(target_file, overwrite=overwrite)
                        if ok:
                            backed += 1
                            self.broadcast(f"[OK] {src_file} -> {target_file}")
                        else:
                            skipped += 1
                    except Exception as e:
                        self.broadcast(f"[ERROR] processing file {fname}: {e}")
                    if self._delay > 0:
                        time.sleep(self._delay)

            self.broadcast(f"[DONE] {src} -> {dest_root} (backed={backed}, skipped={skipped})")
            self.task_queue.task_done()
