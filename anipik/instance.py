import os
from contextlib import contextmanager

from . import config


@contextmanager
def single_instance(path=None):
    """OS lock released on crash; prevents two schedulers submitting the same jobs."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as lock:
        try:
            # Reading the byte another process has locked raises PermissionError on Windows.
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def lock_path():
    return config.DB_PATH.with_suffix(".lock")
