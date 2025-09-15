from pathlib import Path
import os
import threading
import queue
import time
from typing import List

class BackupWorker(threading.Thread):
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.heic', '.ico'}

    def __init__(self, task_queue: queue.Queue, backup_log_path: Path, allowed_roots: List[Path]):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.backup_log_path = Path(backup_log_path)
        self.allowed_roots = [p.resolve() for p in allowed_roots]
        self._clients: List[queue.Queue] = []
        self._backed_up = set()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._load_backed_up()

    def _load_backed_up(self):
        try:
            if self.backup_log_path.exists():
                with self.backup_log_path.open('r', encoding='utf-8') as f:
                    for line in f:
                        self._backed_up.add(line.strip())
        except Exception:
            pass

    def _save_backed_up(self):
        temp = self.backup_log_path.with_suffix('.tmp')
        try:
            with temp.open('w', encoding='utf-8') as f:
                for p in sorted(self._backed_up):
                    f.write(p + "\n")
            os.replace(str(temp), str(self.backup_log_path))
        except Exception as e:
            self.broadcast(f"[ERROR] Failed to persist backup log: {e}")

    def register_client(self):
        q = queue.Queue(maxsize=1000)
        self._clients.append(q)
        return q

    def unregister_client(self, q):
        try:
            self._clients.remove(q)
        except ValueError:
            pass

    def broadcast(self, msg: str):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} {msg}"
        # print to console for container logs
        print(line, flush=True)
        for q in list(self._clients):
            try:
                q.put_nowait(line)
            except queue.Full:
                pass

    def stop(self):
        self._stop_event.set()

    def add_task(self, src: Path, dst: Path, filter_images: bool = True, filter_nfo: bool = True):
        self.task_queue.put({
            'src': str(src),
            'dst': str(dst),
            'filter_images': bool(filter_images),
            'filter_nfo': bool(filter_nfo)
        })
        self.broadcast(f"[QUEUE] Added task: {src} -> {dst}")

    def _is_allowed_path(self, p: Path) -> bool:
        try:
            p = p.resolve()
        except Exception:
            return False
        for root in self.allowed_roots:
            try:
                if p == root or p.is_relative_to(root):
                    return True
            except Exception:
                if str(p).startswith(str(root)):
                    return True
        return False

    def _is_filtered(self, filename: str, filter_images: bool, filter_nfo: bool) -> bool:
        ext = Path(filename).suffix.lower()
        if filter_images and ext in self.IMAGE_EXTS:
            return True
        if filter_nfo and ext == '.nfo':
            return True
        return False

    def _create_placeholder(self, dest_file: Path) -> bool:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_file.with_suffix(dest_file.suffix + '.tmp')
        try:
            with tmp.open('wb') as f:
                f.write(b'\0' * 1024)
            os.replace(str(tmp), str(dest_file))
            return True
        except FileExistsError:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return True
        except Exception as e:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            self.broadcast(f"[ERROR] Failed to create placeholder {dest_file}: {e}")
            return False

    def run(self):
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue

            src = Path(task.get('src'))
            dst = Path(task.get('dst'))
            filter_images = task.get('filter_images', True)
            filter_nfo = task.get('filter_nfo', True)

            self.broadcast(f"[START] {src} -> {dst} (filter_images={filter_images}, filter_nfo={filter_nfo})")

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

            if str(src.resolve()) == str(dst.resolve()):
                self.broadcast(f"[WARN] Source and destination are the same, skipping: {src}")
                self.task_queue.task_done()
                continue

            backed = 0
            skipped = 0

            for dirpath, dirnames, filenames in os.walk(src):
                rel = os.path.relpath(dirpath, src)
                rel = '' if rel == '.' else rel
                for fname in filenames:
                    try:
                        if self._is_filtered(fname, filter_images, filter_nfo):
                            skipped += 1
                            continue
                        src_file = Path(dirpath) / fname
                        src_key = str(src_file.resolve())
                        with self._lock:
                            if src_key in self._backed_up:
                                skipped += 1
                                continue
                        target_dir = dst / rel
                        target_file = target_dir / fname
                        ok = self._create_placeholder(target_file)
                        if ok:
                            with self._lock:
                                self._backed_up.add(src_key)
                            backed += 1
                            self.broadcast(f"[OK] {src_file} -> {target_file}")
                        else:
                            skipped += 1
                    except Exception as e:
                        self.broadcast(f"[ERROR] processing file {fname}: {e}")

            with self._lock:
                self._save_backed_up()

            self.broadcast(f"[DONE] {src} -> {dst} (backed={backed}, skipped={skipped})")
            self.task_queue.task_done()
