"""Backward-compatible re-exports for the original import paths."""
from .paths import discover_mount_points
from .worker import BackupWorker

__all__ = ['BackupWorker', 'discover_mount_points']
