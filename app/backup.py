import os
import shutil
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

            src_dir = task["source"]
            dest_dir = task["dest"]
            self.log_callback(f"开始处理: {src_dir} -> {dest_dir}")

            for root, _, files in os.walk(src_dir):
                # 创建目标目录结构
                rel_path = os.path.relpath(root, src_dir)
                target_dir = os.path.join(dest_dir, rel_path)
                os.makedirs(target_dir, exist_ok=True)

                for f in files:
                    if self._should_skip(f):
                        continue

                    src_file = os.path.join(root, f)
                    dest_file = os.path.join(target_dir, f)
                    
                    with self._lock:
                        if src_file in self._backed_up:
                            self.log_callback(f"已备份，跳过: {src_file}")
                            continue
                        self._backed_up.add(src_file)

                    try:
                        shutil.copy2(src_file, dest_file)  # 保留元数据的复制
                        self.log_callback(f"备份成功: {src_file} -> {dest_file}")
                    except Exception as e:
                        self.log_callback(f"备份失败 {src_file}: {str(e)}")
                    
                    time.sleep(0.01)  # 轻微延迟，避免资源占用过高

            self.log_callback(f"处理完成: {src_dir} -> {dest_dir}")
            self.task_queue.task_done()

    def _should_skip(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        if self.filter_images and ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            return True
        if self.filter_nfo and ext == ".nfo":
            return False  # 改为False表示不过滤nfo文件
        return False

    def stop(self):
        self._stop_event.set()
