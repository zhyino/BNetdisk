\
        # app/backup.py
        from pathlib import Path
        import os
        import threading
        import queue
        import time
        from typing import Dict

        BACKUP_LOG_PATH = Path("/app/backup_log.txt")  # In docker-compose map this to host file
        COMMON_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg", ".heic", ".ico"}

        class BackupWorker:
            def __init__(self):
                self.task_queue: queue.Queue[Dict] = queue.Queue()
                self.clients: list[queue.Queue] = []
                self._backed_up: set[str] = set()
                self._lock = threading.RLock()
                self._load_backed_up()
                self._thread = threading.Thread(target=self._worker_loop, daemon=True)
                self._thread.start()

            def _load_backed_up(self):
                if BACKUP_LOG_PATH.exists():
                    try:
                        with BACKUP_LOG_PATH.open("r", encoding="utf-8") as f:
                            for line in f:
                                self._backed_up.add(line.strip())
                    except Exception as e:
                        print(f"[WARN] failed to read backup log: {e}", flush=True)

            def _save_backed_up(self):
                temp = BACKUP_LOG_PATH.with_suffix(".tmp")
                try:
                    with temp.open("w", encoding="utf-8") as f:
                        for p in sorted(self._backed_up):
                            f.write(p + "\n")
                    os.replace(str(temp), str(BACKUP_LOG_PATH))
                except Exception as e:
                    self.broadcast(f"[ERROR] Failed to write backup log: {e}")

            def add_task(self, src: str, dest: str, filter_images: bool = True, filter_nfo: bool = True):
                task = {"src": src, "dest": dest, "filter_images": bool(filter_images), "filter_nfo": bool(filter_nfo)}
                self.task_queue.put(task)
                self.broadcast(f"[QUEUE] Added task: {src} -> {dest}")

            def _is_filtered(self, filename: str, filter_images: bool, filter_nfo: bool) -> bool:
                ext = Path(filename).suffix.lower()
                if filter_images and ext in COMMON_IMAGE_EXTS:
                    return True
                if filter_nfo and ext == ".nfo":
                    return True
                return False

            def _worker_loop(self):
                while True:
                    task = self.task_queue.get()
                    try:
                        self._process_task(task)
                    except Exception as e:
                        self.broadcast(f"[ERROR] Task exception: {e}")
                    finally:
                        with self._lock:
                            self._save_backed_up()
                        self.task_queue.task_done()

            def _process_task(self, task: Dict):
                src = Path(task["src"]).expanduser().resolve()
                dest = Path(task["dest"]).expanduser().resolve()
                filter_images = task["filter_images"]
                filter_nfo = task["filter_nfo"]

                self.broadcast(f"[START] {src} -> {dest} (filter_images={filter_images}, filter_nfo={filter_nfo})")

                if not src.exists() or not src.is_dir():
                    self.broadcast(f"[ERROR] Source not exists or not dir: {src}")
                    return

                # check dest is not inside src
                try:
                    if os.path.commonpath([str(src)]) == os.path.commonpath([str(src), str(dest)]):
                        self.broadcast(f"[ERROR] Destination must not be source or its subdir: {dest}")
                        return
                except Exception:
                    if str(dest).startswith(str(src)):
                        self.broadcast(f"[ERROR] Destination must not be source or its subdir: {dest}")
                        return

                dest.mkdir(parents=True, exist_ok=True)

                num_backed = 0
                num_skipped = 0

                for dirpath, dirnames, filenames in os.walk(src):
                    rel = os.path.relpath(dirpath, src)
                    rel = "" if rel == "." else rel
                    target_dir = dest.joinpath(rel)
                    try:
                        target_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        self.broadcast(f"[WARN] Failed to create dir {target_dir}: {e}")
                        continue

                    for fname in filenames:
                        src_file = Path(dirpath).joinpath(fname).resolve()
                        src_file_key = str(src_file)
                        if src_file_key in self._backed_up:
                            num_skipped += 1
                            continue
                        if self._is_filtered(fname, filter_images, filter_nfo):
                            num_skipped += 1
                            self.broadcast(f"[SKIP] Filtered: {src_file}")
                            continue
                        dest_file = target_dir.joinpath(fname)
                        try:
                            with dest_file.open("wb") as f:
                                f.write(b"\\0" * 1024)
                            with self._lock:
                                self._backed_up.add(src_file_key)
                            num_backed += 1
                            self.broadcast(f"[OK] {src_file} -> {dest_file} (backed:{num_backed} skipped:{num_skipped})")
                        except Exception as e:
                            self.broadcast(f"[ERROR] Write file failed {dest_file}: {e}")

                self.broadcast(f"[DONE] Finished: {src} -> {dest} (backed:{num_backed} skipped:{num_skipped})")

            # SSE client management
            def register_client(self):
                q = queue.Queue(maxsize=1000)
                self.clients.append(q)
                return q

            def unregister_client(self, q):
                try:
                    self.clients.remove(q)
                except ValueError:
                    pass

            def broadcast(self, message: str):
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                line = f"{ts} {message}"
                print(line, flush=True)
                for q in list(self.clients):
                    try:
                        q.put_nowait(line)
                    except queue.Full:
                        pass

        # single worker instance
        worker = BackupWorker()
