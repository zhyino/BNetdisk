"""Path discovery, allow-list checks, and destination layout helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence


SKIP_FS_TYPES = frozenset({
    'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'cgroup', 'cgroup2',
    'overlay', 'squashfs', 'debugfs', 'tracefs', 'securityfs',
    'ramfs', 'rootfs', 'fusectl', 'mqueue',
})
SKIP_ROOTS = frozenset({'/', '/proc', '/sys', '/dev'})


def discover_mount_points() -> List[Path]:
    roots = set()
    try:
        with open('/proc/mounts', 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount_point = parts[1]
                fs_type = parts[2] if len(parts) > 2 else ''
                if fs_type in SKIP_FS_TYPES:
                    continue
                if not mount_point.startswith('/'):
                    continue
                roots.add(mount_point)
    except OSError:
        for candidate in ('/mnt', '/media', '/data', '/srv', '/Volumes', '/Users'):
            if Path(candidate).exists():
                roots.add(candidate)

    for candidate in ('/app/data', '/app'):
        if Path(candidate).exists():
            roots.add(candidate)

    return [Path(item) for item in sorted(roots) if item not in SKIP_ROOTS]


def normalize_roots(items: Iterable) -> List[Path]:
    normalized: List[Path] = []
    seen = set()
    for item in items:
        try:
            path = Path(item).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(path)
    return normalized


def parse_allowed_roots_env(value: str) -> List[Path]:
    if not value:
        return []
    return normalize_roots(re.split(r'\s*,\s*', value) if value else [])


def path_under_root(path: Path, root: Path) -> bool:
    try:
        path = path.resolve()
        root = root.resolve()
    except (OSError, RuntimeError):
        return False
    try:
        return path == root or path.is_relative_to(root)
    except AttributeError:
        path_str = str(path)
        root_str = str(root)
        return path_str == root_str or path_str.startswith(root_str.rstrip('/') + '/')
    except (OSError, RuntimeError, ValueError):
        return False


def is_allowed_path(path: Path, allowed_roots: Sequence[Path], extra_roots: Sequence[Path] | None = None) -> bool:
    try:
        path = path.resolve()
    except (OSError, RuntimeError):
        return False
    roots = list(allowed_roots)
    if extra_roots:
        roots.extend(extra_roots)
    for root in roots:
        if path_under_root(path, root):
            return True
    return False


def build_dest_final(src: Path, dst: Path) -> Path:
    """Preserve absolute source structure under the selected destination.

    Example: src=/CloudDrive/Movies, dst=/115 -> /115/CloudDrive/Movies
    """
    try:
        return dst / src.relative_to(src.anchor)
    except (ValueError, RuntimeError):
        return dst / src.name


def parent_path(path: str) -> str:
    if not path or path == '/':
        return '/'
    cleaned = path.rstrip('/')
    idx = cleaned.rfind('/')
    if idx <= 0:
        return '/'
    return cleaned[:idx] or '/'
