import os
import time
import json
import queue
import threading
from pathlib import Path
from typing import Set, List, Dict, Optional

class BackupWorker(threading.Thread):
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.heic', '.ico'}
    MAX_SERVICE_LOG_BYTES = 500_000  # 500KB
    LOG_ROTATION_COUNT = 5
    MAX_BACKED_UP_ENTRIES = 500_000  # 限制备份记录数量

    def __init__(self, service_log: Path, backup_log: Path):
        super().__init__(daemon=True)
        self.service_log = service_log
        self.backup_log = backup_log
        self.task_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._message_queue = queue.Queue(maxsize=1000)
        self._backed_up: Set[str] = set()
        self._lock = threading.Lock()

    def run(self):
        count = self._load_backed_up_tail(max_lines=100000)
        if count:
            self.broadcast(f"[INFO] Loaded {count} entries from backup_log (tail).")
        else:
            self.broadcast(f"[INFO] No existing backup_log entries loaded or empty file.")

        batch_size = 1000
        processed_count = 0
        
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                with self._lock:
                    if len(self._backed_up) > self.MAX_BACKED_UP_ENTRIES:
                        self._backed_up = set(list(self._backed_up)[-self.MAX_BACKED_UP_ENTRIES:])
                continue

            src = Path(task.get('src'))
            dst = Path(task.get('dst'))
            filter_images = task.get('filter_images', True)
            filter_nfo = task.get('filter_nfo', True)
            mirror = task.get('mirror', True)
            mode = task.get('mode', 'incremental')

            self.broadcast(f"[START] {src} -> {dst} (filter_images={filter_images}, filter_nfo={filter_nfo}, mirror={mirror}, mode={mode})")

            try:
                if not src.exists() or not src.is_dir():
                    self.broadcast(f"[ERROR] Source directory {src} does not exist or is not a directory")
                    continue

                os.makedirs(dst, exist_ok=True)
                self._process_directory(src, dst, filter_images, filter_nfo, mirror, mode)
                self.broadcast(f"[COMPLETE] Task {src} -> {dst} finished")
            except Exception as e:
                self.broadcast(f"[ERROR] Task failed: {str(e)}")
            finally:
                processed_count += 1
                if processed_count % batch_size == 0:
                    self._save_backed_up()
                    time.sleep(0.1)
                self.task_queue.task_done()

    def _process_directory(self, src: Path, dst: Path, filter_images: bool, filter_nfo: bool, mirror: bool, mode: str):
        for root, dirs, files in os.walk(src):
            rel_path = Path(root).relative_to(src)
            target_dir = dst / rel_path
            
            os.makedirs(target_dir, exist_ok=True)
            
            for file in files[:100]:
                src_file = Path(root) / file
                dst_file = target_dir / file
                
                if self._should_filter_file(src_file, filter_images, filter_nfo):
                    continue
                    
                file_key = str(src_file)
                with self._lock:
                    if mode == 'incremental' and file_key in self._backed_up:
                        continue
                
                try:
                    self._create_placeholder(dst_file)
                    with self._lock:
                        self._backed_up.add(file_key)
                    self._append_backup_log(file_key)
                    self.broadcast(f"[CREATED] {dst_file}")
                except Exception as e:
                    self.broadcast(f"[ERROR] Failed to create {dst_file}: {str(e)}")
            
            dirs[:] = dirs[:10]

    def _should_filter_file(self, file: Path, filter_images: bool, filter_nfo: bool) -> bool:
        ext = file.suffix.lower()
        if filter_images and ext in self.IMAGE_EXTS:
            return True
        if filter_nfo and ext == '.nfo':
            return True
        return False

    def _create_placeholder(self, file: Path):
        if file.exists():
            return
            
        try:
            with open(file, 'wb') as f:
                f.write(b'\0' * 1024)  # 1KB占位文件
        except Exception as e:
            raise Exception(f"Failed to create placeholder: {str(e)}")

    def _load_backed_up_tail(self, max_lines: int = 100000) -> int:
        if not self.backup_log.exists():
            return 0
            
        try:
            lines = []
            with open(self.backup_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # 只加载最后max_lines行
            lines = lines[-max_lines:]
            with self._lock:
                self._backed_up = set(line.strip() for line in lines if line.strip())
            return len(self._backed_up)
        except Exception as e:
            self.broadcast(f"[ERROR] Failed to load backup log: {str(e)}")
            return 0

    def _save_backed_up(self):
        try:
            temp = self.backup_log.with_suffix('.tmp')
            with temp.open('w', encoding='utf-8') as f:
                for p in sorted(self._backed_up):
                    f.write(p + "\n")
            
            if self.backup_log.exists():
                self.backup_log.unlink()
            temp.rename(self.backup_log)
        except Exception as e:
            self.broadcast(f"[ERROR] Failed to save backup log: {str(e)}")

    def _append_backup_log(self, entry: str):
        try:
            with open(self.backup_log, 'a', encoding='utf-8') as f:
                f.write(entry + "\n")
        except Exception as e:
            self.broadcast(f"[ERROR] Failed to append to backup log: {str(e)}")

    def _append_service_log(self, msg: str):
        try:
            with open(self.service_log, 'a', encoding='utf-8') as f:
                f.write(msg + "\n")
        except Exception as e:
            print(f"Failed to write to service log: {e}")
            return
        
        try:
            if self.service_log.exists():
                size = self.service_log.stat().st_size
                if size > self.MAX_SERVICE_LOG_BYTES:
                    for i in range(self.LOG_ROTATION_COUNT - 1, 0, -1):
                        old_log = f"{self.service_log}.{i}"
                        new_log = f"{self.service_log}.{i+1}"
                        if os.path.exists(old_log):
                            if os.path.exists(new_log):
                                os.remove(new_log)
                            os.rename(old_log, new_log)
                    
                    os.rename(self.service_log, f"{self.service_log}.1")
                    with open(self.service_log, 'w', encoding='utf-8') as f:
                        pass
        except Exception as e:
            print(f"Failed to rotate logs: {e}")

    def broadcast(self, msg: str):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        full_msg = f"[{timestamp}] {msg}"
        self._append_service_log(full_msg)
        
        try:
            self._message_queue.put_nowait(full_msg)
        except queue.Full:
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(full_msg)
            except:
                pass

    def get_message(self, timeout: float = 0.1) -> Optional[str]:
        try:
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_last_logs(self, lines: int = 200) -> List[str]:
        if not self.service_log.exists():
            return []
        return tail_file_lines(self.service_log, lines)

    def add_task(self, task: Dict):
        self.task_queue.put(task)

    def queue_size(self) -> int:
        return self.task_queue.qsize()

    def stop(self):
        self._stop_event.set()
        self.join()

# 导入app模块中的tail_file_lines函数
from app.app import tail_file_lines
