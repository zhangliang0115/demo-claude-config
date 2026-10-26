"""Exclusive advisory lock on a lock file: fcntl on POSIX, msvcrt on Windows.

When neither is importable, raise the caller's message so writes are refused, never unlocked.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import time

WINDOWS_RETRY_SECONDS = 0.05


def _backend():
    try:
        import fcntl
        return 'fcntl', fcntl
    except ImportError:
        pass
    try:
        import msvcrt
        return 'msvcrt', msvcrt
    except ImportError:
        return None, None


@contextmanager
def exclusive(lock_path, unsupported_message):
    kind, module = _backend()
    if kind is None:
        raise ValueError(unsupported_message)
    lock_path = Path(lock_path)
    if lock_path.is_symlink():
        raise ValueError('写锁文件不能为符号链接')
    with lock_path.open('a+b') as stream:
        if kind == 'fcntl':
            module.flock(stream.fileno(), module.LOCK_EX)
        else:
            # msvcrt 锁定字节区间；LK_LOCK 只重试约 10 秒，这里持续等待以匹配 flock 的阻塞语义
            stream.seek(0)
            while True:
                try:
                    module.locking(stream.fileno(), module.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(WINDOWS_RETRY_SECONDS)
        try:
            yield
        finally:
            if kind == 'fcntl':
                module.flock(stream.fileno(), module.LOCK_UN)
            else:
                stream.seek(0)
                module.locking(stream.fileno(), module.LK_UNLCK, 1)


def copy_mode(stream, target):
    """Keep the target's permission bits on a replacement file; Windows has no fchmod."""
    mode = Path(target).stat().st_mode & 0o777
    if hasattr(os, 'fchmod'):
        os.fchmod(stream.fileno(), mode)
    else:
        os.chmod(stream.name, mode)
