"""Buffered service log writer with in-memory tail support."""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from pathlib import Path


class ServiceLogWriter(threading.Thread):
    def __init__(self, path: Path, max_lines_keep: int = 5000):
        super().__init__(daemon=True, name='service-log-writer')
        self.path = Path(path)
        self.queue: queue.Queue = queue.Queue(maxsize=10000)
        self.deque: deque = deque(maxlen=max_lines_keep)
        self._stop = threading.Event()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def run(self) -> None:
        buf = []
        last_flush = time.time()
        while not self._stop.is_set():
            try:
                item = self.queue.get(timeout=1)
                if item is not None:
                    buf.append(item)
                    self.deque.append(item)
            except queue.Empty:
                pass

            if buf and (len(buf) >= 50 or (time.time() - last_flush) > 1 or self._stop.is_set()):
                self._flush(buf)
                buf = []
                last_flush = time.time()

        if buf:
            self._flush(buf)

    def _flush(self, lines) -> None:
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass

    def append(self, line: str) -> None:
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            pass

    def tail_lines(self, n: int = 100):
        return list(self.deque)[-n:]
