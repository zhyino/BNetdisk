"""Background worker that creates video placeholder files."""
from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .config import PLACEHOLDER_SIZE, VIDEO_EXTS
from .logging_service import ServiceLogWriter
from .paths import discover_mount_points, is_allowed_path, path_under_root


class BackupWorker(threading.Thread):
    def __init__(
        self,
        task_queue: queue.Queue,
        backup_dir: Path,
        allowed_roots: Sequence[Path],
        ops_per_sec: float = 20.0,
        service_log_path: Optional[Path] = None,
    ):
        super().__init__(daemon=True, name='backup-worker')
        self.task_queue = task_queue
        self.backup_dir = Path(backup_dir)
        self.allowed_roots: List[Path] = []
        for root in allowed_roots:
            try:
                self.allowed_roots.append(Path(root).resolve())
            except (OSError, RuntimeError):
                continue

        self._clients: List[queue.Queue] = []
        self._clients_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._current_task: Optional[Dict] = None
        self._stats_lock = threading.RLock()
        self._last_result: Optional[Dict] = None

        try:
            initial_rate = float(os.environ.get('BACKUP_RATE', str(ops_per_sec)))
        except (TypeError, ValueError):
            initial_rate = ops_per_sec
        self._rate_lock = threading.RLock()
        self.ops_per_sec = 0.0
        self._delay = 0.0

        if service_log_path is None:
            service_log_path = self.backup_dir / 'service_log.txt'
        self.service_writer = ServiceLogWriter(service_log_path)
        self.service_writer.start()
        # Apply after logger exists so the rate change is recorded cleanly.
        self.set_rate(initial_rate)

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self.service_writer.stop()
        except Exception:
            pass

    def broadcast(self, msg: str) -> None:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f'{ts} {msg}'
        writer = getattr(self, 'service_writer', None)
        if writer is not None:
            try:
                writer.append(line)
            except Exception:
                pass
        with self._clients_lock:
            for client_q in list(self._clients):
                try:
                    client_q.put_nowait(line)
                except queue.Full:
                    pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def register_client(self) -> queue.Queue:
        client_q: queue.Queue = queue.Queue(maxsize=1000)
        with self._clients_lock:
            self._clients.append(client_q)
        try:
            client_q.put_nowait('[INFO] connected')
            for line in self.service_writer.tail_lines(100):
                try:
                    client_q.put_nowait(line)
                except queue.Full:
                    break
        except queue.Full:
            pass
        return client_q

    def unregister_client(self, client_q: queue.Queue) -> None:
        with self._clients_lock:
            try:
                self._clients.remove(client_q)
            except ValueError:
                pass

    def set_rate(self, ops_per_sec: float) -> float:
        """Update generation speed at runtime. 0 means unlimited."""
        try:
            rate = float(ops_per_sec)
        except (TypeError, ValueError) as exc:
            raise ValueError('invalid rate') from exc
        if rate < 0:
            raise ValueError('rate must be >= 0')
        # Soft upper bound protects remote mounts from accidental overload.
        if rate > 5000:
            rate = 5000.0
        with self._rate_lock:
            self.ops_per_sec = rate
            self._delay = 0.0 if rate <= 0 else max(0.0, 1.0 / rate)
            applied = self.ops_per_sec
        self.broadcast(f'[INFO] Backup rate set to {applied:g} ops/sec' + (' (unlimited)' if applied <= 0 else ''))
        return applied

    def get_rate(self) -> float:
        with self._rate_lock:
            return float(self.ops_per_sec)

    def _sleep_for_rate(self) -> None:
        with self._rate_lock:
            delay = self._delay
        if delay > 0:
            time.sleep(delay)

    def get_status(self) -> Dict:
        with self._stats_lock:
            current = self._current_task
            last_result = self._last_result
        return {
            'running': not self._stop_event.is_set(),
            'queue_size': self.task_queue.qsize(),
            'current': current,
            'last_result': last_result,
            'ops_per_sec': self.get_rate(),
            'videos_only': True,
        }

    def _is_allowed_path(self, path: Path) -> bool:
        return is_allowed_path(path, self.allowed_roots, discover_mount_points())

    @staticmethod
    def is_video_file(filename: str) -> bool:
        return Path(filename).suffix.lower() in VIDEO_EXTS

    def should_skip(self, filename: str, videos_only: bool = True) -> bool:
        if videos_only:
            return not self.is_video_file(filename)
        return False

    def _create_placeholder(self, dest_file: Path, overwrite: bool = False) -> bool:
        try:
            if dest_file.exists() and not overwrite:
                return True
        except OSError:
            pass

        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.broadcast(f'[ERROR] Cannot create parent directories for {dest_file}: {exc}')
            return False

        tmp = dest_file.parent / f'.{dest_file.name}.{os.getpid()}.{threading.get_ident()}.tmp'
        try:
            with tmp.open('wb') as handle:
                handle.write(b'\0' * PLACEHOLDER_SIZE)
            os.replace(str(tmp), str(dest_file))
            return True
        except OSError as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            self.broadcast(f'[ERROR] Failed to create placeholder {dest_file}: {exc}')
            return False

    def add_task(
        self,
        src: Path,
        dst: Path,
        videos_only: bool = True,
        mirror: bool = False,
        mode: str = 'incremental',
    ) -> None:
        payload = {
            'src': str(src),
            'dst': str(dst),
            'videos_only': bool(videos_only),
            'mirror': bool(mirror),
            'mode': str(mode),
        }
        self.task_queue.put(payload)
        self.broadcast(
            f'[QUEUE] Added task: {src} -> {dst} '
            f'(mode={mode}, videos_only={videos_only})'
        )

    def run(self) -> None:
        self.broadcast('[INFO] Worker started')
        while not self._stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._process_task(task)
            finally:
                self.task_queue.task_done()

    def _process_task(self, task: Dict) -> None:
        src = Path(task.get('src', ''))
        dst = Path(task.get('dst', ''))
        videos_only = bool(task.get('videos_only', True))
        mirror = bool(task.get('mirror', False))
        mode = task.get('mode', 'incremental') or 'incremental'

        with self._stats_lock:
            self._current_task = {
                'src': str(src),
                'dst': str(dst),
                'mode': mode,
                'videos_only': videos_only,
            }

        self.broadcast(
            f'[START] {src} -> {dst} '
            f'(videos_only={videos_only}, mirror={mirror}, mode={mode})'
        )

        if not self._is_allowed_path(src):
            self.broadcast(f'[WARN] Source not allowed: {src}')
            self._finish(None)
            return
        if not self._is_allowed_path(dst):
            self.broadcast(f'[WARN] Destination not allowed: {dst}')
            self._finish(None)
            return
        if not src.exists() or not src.is_dir():
            self.broadcast(f'[WARN] Source missing or not a directory: {src}')
            self._finish(None)
            return

        try:
            dst.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.broadcast(f'[WARN] Cannot create destination {dst}: {exc}')
            self._finish(None)
            return

        try:
            src_name = src.resolve().name
        except (OSError, RuntimeError):
            src_name = src.name
        try:
            dst_name = dst.resolve().name
        except (OSError, RuntimeError):
            dst_name = dst.name

        dest_root = dst / src_name if (mirror and dst_name != src_name) else dst

        try:
            if dest_root.resolve() == src.resolve() or path_under_root(dest_root, src):
                self.broadcast(
                    f'[WARN] Computed destination would be same as or inside source, skipping: {dest_root}'
                )
                self._finish(None)
                return
        except (OSError, RuntimeError):
            self.broadcast(f'[WARN] Could not resolve paths safely for {src} -> {dest_root}, skipping')
            self._finish(None)
            return

        backed = 0
        skipped = 0
        overwrite = mode == 'full'

        for dirpath, _dirnames, filenames in os.walk(src):
            if self._stop_event.is_set():
                break
            rel = os.path.relpath(dirpath, src)
            rel = '' if rel == '.' else rel
            for fname in filenames:
                try:
                    if self.should_skip(fname, videos_only=videos_only):
                        skipped += 1
                        continue
                    src_file = Path(dirpath) / fname
                    target_file = dest_root / rel / fname
                    try:
                        if target_file.exists() and not overwrite:
                            skipped += 1
                            continue
                    except OSError:
                        pass
                    if self._create_placeholder(target_file, overwrite=overwrite):
                        backed += 1
                        self.broadcast(f'[OK] {src_file} -> {target_file}')
                    else:
                        skipped += 1
                except Exception as exc:  # noqa: BLE001 - keep worker alive
                    self.broadcast(f'[ERROR] processing file {fname}: {exc}')
                self._sleep_for_rate()

        result = {
            'src': str(src),
            'dst': str(dest_root),
            'backed': backed,
            'skipped': skipped,
            'mode': mode,
        }
        self.broadcast(f'[DONE] {src} -> {dest_root} (backed={backed}, skipped={skipped})')
        self._finish(result)

    def _finish(self, result: Optional[Dict]) -> None:
        with self._stats_lock:
            self._current_task = None
            if result is not None:
                self._last_result = result
