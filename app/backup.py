import os
import threading
import queue
import time

class BackupWorker(threading.Thread):
    def __init__(self, task_queue, log_callback, filter_images=True, filter_nfo=False):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.log_callback = log_callback
        self.filter_images = filter_images
        self.filter_nfo = filter_nfo
        self._stop_event = threading.Event()
        self._backed_up = set()
        self._lock = threading.RLock()

    def run(self):
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue

            src_dir = task["path"]
            self.log_callback(f"开始处理目录: {src_dir}")

            for root, _, files in os.walk(src_dir):
                for f in files:
                    if self._should_skip(f):
                        continue

                    full_path = os.path.join(root, f)
                    with self._lock:
                        if full_path in self._backed_up:
                            continue
                        self._backed_up.add(full_path)

                    self.log_callback(f"备份文件: {full_path}")
                    time.sleep(0.1)

            self.log_callback(f"目录处理完成: {src_dir}")
            self.task_queue.task_done()

    def _should_skip(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        if self.filter_images and ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            return True
        if self.filter_nfo and ext == ".nfo":
            return True
        return False

    def stop(self):
        self._stop_event.set()
