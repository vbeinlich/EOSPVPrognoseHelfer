"""Private, bounded, durable file primitives; no source writes or network."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path


class WorkerError(ValueError):
    """Only fixed public reason codes may be used as messages."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def directory(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise WorkerError("unsafe_directory")
    return path


def read(path, limit=32_000_000):
    path = Path(path)
    directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise WorkerError("unsafe_or_oversized_file")
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or len(raw) != before.st_size:
                raise WorkerError("input_changed_during_read")
            current = path.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ):
                raise WorkerError("input_changed_during_read")
            return raw
    except FileNotFoundError:
        raise WorkerError("input_missing") from None
    except OSError:
        raise WorkerError("input_unreadable_or_unsafe") from None


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, raw, *, immutable=False):
    path = Path(path)
    directory(path.parent)
    if path.is_symlink():
        raise WorkerError("unsafe_destination")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".writing-", delete=False) as h:
            temporary = Path(h.name)
            os.fchmod(h.fileno(), 0o400 if immutable else 0o600)
            h.write(raw)
            h.flush()
            os.fsync(h.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if read(path, len(raw)) != raw:
                    raise WorkerError("immutable_conflict") from None
        else:
            os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def setup(source, workspace):
    source = directory(source).resolve(strict=True)
    workspace = directory(workspace).resolve(strict=True)
    if source == workspace or source in workspace.parents or workspace in source.parents:
        raise WorkerError("source_workspace_overlap")
    if workspace.stat().st_mode & 0o077:
        raise WorkerError("workspace_not_private")
    for name in ("verified", "receipts", "pending", "rejected", "state", "logs"):
        path = workspace / name
        path.mkdir(mode=0o700, exist_ok=True)
        directory(path)
        if path.stat().st_mode & 0o077:
            raise WorkerError("workspace_not_private")
    return source, workspace
