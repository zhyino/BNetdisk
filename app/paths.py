"""Path discovery, allow-list checks, and destination layout helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


SKIP_FS_TYPES = frozenset({
    'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'cgroup', 'cgroup2',
    'overlay', 'squashfs', 'debugfs', 'tracefs', 'securityfs',
    'ramfs', 'rootfs', 'fusectl', 'mqueue', 'pstore', 'bpf',
    'configfs', 'devpts', 'hugetlbfs', 'autofs', 'nsfs',
})

# Exact roots that should never appear in the directory browser.
SKIP_ROOTS = frozenset({
    '/',
    '/proc', '/sys', '/dev', '/run', '/tmp',
    '/boot', '/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64',
    '/var', '/opt', '/root', '/home',
    '/app',  # container app code, not a media volume
})

# Prefixes treated as container/system internals (hidden from browser roots).
INTERNAL_PREFIXES = (
    '/proc/', '/sys/', '/dev/', '/run/', '/tmp/',
    '/boot/', '/etc/', '/usr/', '/bin/', '/sbin/', '/lib/', '/lib64/',
    '/var/lib/', '/var/run/', '/var/cache/', '/var/log/', '/var/spool/',
    '/root/',
    '/app/',  # hide /app and /app/data from mount picker
    '/snap/',
    '/lost+found',
)

# Preferred host/container volume locations for non-Linux fallbacks.
FALLBACK_CANDIDATES = (
    '/mnt', '/media', '/data', '/srv', '/share', '/shares',
    '/volume1', '/volume2', '/volume3',
    '/Volumes', '/Users',
)


def _is_internal_path(path: str) -> bool:
    if not path or path in SKIP_ROOTS:
        return True
    if path in ('/app', '/app/data'):
        return True
    for prefix in INTERNAL_PREFIXES:
        if path == prefix.rstrip('/') or path.startswith(prefix):
            return True
    # Hide very deep system-looking paths (usually container noise).
    parts = [p for p in path.split('/') if p]
    if len(parts) >= 5 and parts[0] in {'var', 'usr', 'etc', 'run', 'proc', 'sys', 'dev', 'app'}:
        return True
    return False


def _path_exists_dir(path: str) -> bool:
    try:
        p = Path(path)
        return p.exists() and p.is_dir()
    except OSError:
        return False


def discover_mount_points() -> List[Path]:
    """Return browser-friendly mount roots, excluding container internals."""
    roots: set[str] = set()

    try:
        with open('/proc/mounts', 'r', encoding='utf-8', errors='ignore') as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount_point = parts[1]
                fs_type = parts[2]
                if fs_type in SKIP_FS_TYPES:
                    continue
                if not mount_point.startswith('/'):
                    continue
                # /proc/mounts escapes spaces as \040
                mount_point = mount_point.replace('\040', ' ')
                if _is_internal_path(mount_point):
                    continue
                if not _path_exists_dir(mount_point):
                    continue
                roots.add(mount_point)
    except OSError:
        for candidate in FALLBACK_CANDIDATES:
            if _path_exists_dir(candidate) and not _is_internal_path(candidate):
                roots.add(candidate)

    # Always include common volume parents when present (even if not separate mounts).
    for candidate in FALLBACK_CANDIDATES:
        if _path_exists_dir(candidate) and not _is_internal_path(candidate):
            roots.add(candidate)

    # Prefer shorter roots first, drop children when a parent root already exists
    # only if child is clearly nested under a selected parent *and* not a real separate
    # user mount we still want. Keep all non-internal mounts, but sort usefully.
    cleaned = sorted(roots, key=lambda item: (item.count('/'), item.lower()))
    return [Path(item) for item in cleaned]


def list_browser_roots(limit: int = 200) -> List[str]:
    """Public helper used by the web UI mount picker."""
    points = discover_mount_points()
    out: List[str] = []
    seen = set()
    for path in points:
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


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


def is_allowed_path(path: Path, allowed_roots: Sequence[Path], extra_roots: Optional[Sequence[Path]] = None) -> bool:
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
