"""Moving a subscription's library folder when its save directory changes."""
import os
import shutil
from pathlib import Path


class FolderMoveError(Exception):
    """The move is unsafe (would overwrite or nest); nothing was changed."""


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def move_folder(old, new):
    """Move directory `old` to `new`. Returns "moved", "missing" (no old folder) or "same".

    Refuses (FolderMoveError) to merge into a non-empty folder or to move a folder into
    itself. An empty target folder is replaced. A case-only rename is done in place.
    """
    old, new = Path(os.path.abspath(old)), Path(os.path.abspath(new))
    if str(old) == str(new):
        return "same"
    if not old.exists():
        return "missing"
    if not old.is_dir():
        raise FolderMoveError(f"不是文件夹：{old}")
    if same_path(old, new):  # only letter case differs (Windows paths are case-insensitive)
        os.rename(old, new)
        return "moved"
    if os.path.normcase(str(new)).startswith(os.path.normcase(str(old)) + os.sep):
        raise FolderMoveError("新目录不能放在旧目录里面")
    if new.exists():
        if not new.is_dir() or any(new.iterdir()):
            raise FolderMoveError(f"目标文件夹已存在且不为空，没有移动：{new}")
        new.rmdir()
    new.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old), str(new))  # a rename on the same drive; copy + delete across drives
    return "moved"
