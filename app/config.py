"""Runtime configuration for BNetdisk."""
from __future__ import annotations

import os
from pathlib import Path


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


APP_PORT = _int_env('APP_PORT', 18008)
BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', '/app/data')).resolve()
BACKUP_RATE = _float_env('BACKUP_RATE', 20.0)
ALLOWED_ROOTS_ENV = os.environ.get('ALLOWED_ROOTS', '').strip()
SERVICE_LOG = BACKUP_DIR / 'service_log.txt'
PLACEHOLDER_SIZE = 1024
MAX_LIST_ENTRIES = 10000
MAX_LOG_LINES = 100
SSE_KEEPALIVE_SECONDS = 15

# Only these extensions become placeholder files.
VIDEO_EXTS = frozenset({
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.m4v', '.mpg', '.mpeg', '.m2ts', '.mts', '.ts', '.vob',
    '.iso', '.rmvb', '.rm', '.3gp', '.ogv', '.f4v', '.asf',
    '.divx', '.xvid', '.tp', '.trp', '.mxf',
})

# Kept for documentation / optional non-whitelist modes.
IMAGE_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    '.tiff', '.svg', '.heic', '.ico',
})
SUBTITLE_EXTS = frozenset({
    '.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx', '.sup',
    '.smi', '.sami', '.lrc', '.ttml', '.dfxp', '.mks',
})
