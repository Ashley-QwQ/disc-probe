"""Cross-process exclusion for optical-drive operations."""
from contextlib import contextmanager
from functools import wraps
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import uuid

from .sectors import state_path


def user_state():
    return Path(state_path()).parent


class FileLocked(Exception):
    pass


@contextmanager
def file_lock(path, *, wait=False, create=True):
    # Keep the file: unlinking it could let a second process lock a different inode.
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | (os.O_CREAT if create else 0) | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "r+b", buffering=0) as stream:
        if os.name == "nt":
            import msvcrt
            import time
            while True:
                stream.seek(0)
                try:
                    # Windows permits locking a byte beyond EOF.
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if not wait:
                        raise FileLocked from None
                    time.sleep(.025)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                raise FileLocked from None
        yield stream  # Closing the descriptor releases the lock, including on process exit.


_ACTIONS = {
    "burn": "刻录", "erase": "擦除", "info": "读取光驱信息", "disc": "检查光盘",
    "whois": "读取光盘身份", "swap": "等待换盘", "timing": "计时测量",
    "geo": "几何测量", "label": "读取光盘会话", "verify": "刻后验证",
    "calibrate": "校准",
}


class DriveBusy(RuntimeError):
    code = "drive_busy"
    exit_code = 75

    def __init__(self, owner):
        self.owner = owner
        pid, action = owner.get("pid"), owner.get("action")
        known = type(pid) is int and isinstance(action, str) and action in _ACTIONS
        zh = f"（pid {pid}，正在：{_ACTIONS[action]}）" if known else ""
        en = f" (pid {pid}, action: {action})" if known else ""
        super().__init__(f"这台光驱正在被另一个窗口或命令使用{zh}。等它结束再试。 / "
                         f"This drive is in use by another window or command{en}. Wait for it to finish and try again.")


def drive_key(drive):
    value = os.fspath(drive).strip()
    letter = re.fullmatch(r"(?:\\\\[.?]\\)?([a-z])[:\\/]*", value, re.IGNORECASE)
    if letter:
        return letter[1].upper()
    if sys.platform.startswith("linux"):
        from .sg import _resolve, _sg_for_sr
        value = os.path.realpath(_resolve(value))
        if re.fullmatch(r"/dev/sr\d+", value):
            value = _sg_for_sr(value) or value
    else:
        value = os.path.normcase(os.path.realpath(value))
    return hashlib.sha256(os.fsencode(value)).hexdigest()


def _owner(path):
    try:
        with path.open("rb") as stream:
            stream.seek(1)
            value = json.loads(stream.read(1024))
        if isinstance(value, dict):
            return value
    except (OSError, ValueError):
        pass
    return {}


_held = threading.local()
_virtual_root = None  # Set by Disc Lab's device hook only in virtual-drive processes.
_PARENT_LEASE = "DISCPROBE_PARENT_DRIVE_LEASE"


def _lock_dir():
    root = user_state() / "drive-locks"
    if _virtual_root is not None:
        lab = os.path.normcase(os.path.realpath(_virtual_root))
        root = root / hashlib.sha256(os.fsencode(lab)).hexdigest()
    return root


def _lock_path(drive):
    return _lock_dir() / (drive_key(drive) + ".lock")


def _lane(path, name):
    return path.with_suffix('.' + name)


@contextmanager
def _acquire(path, *, create=True):
    try:
        with file_lock(path, create=create) as stream:
            yield stream
    except FileLocked:
        raise DriveBusy(_owner(path)) from None


@contextmanager
def _gate(path, *, create=True):
    with _acquire(path, create=create) as stream:
        # A child can outlive a killed parent. Once we hold the gate, old
        # children cannot start, and existing children still exclude us.
        for lane in ('worker', 'native'):
            try:
                with _acquire(_lane(path, lane), create=False):
                    pass
            except FileNotFoundError:
                pass
        yield stream


def _save_owner(stream, owner):
    stream.seek(1)
    stream.write(json.dumps(owner).encode('utf-8'))
    stream.truncate()


def child_env(drive):
    """Give a direct child a distinct lease under the operation already held."""
    path = _lock_path(drive)
    held = getattr(_held, 'paths', {}).get(path)
    env = dict(os.environ)
    env.pop(_PARENT_LEASE, None)
    if held is not None:
        lane, token = held
        env[_PARENT_LEASE] = json.dumps(dict(path=str(path), owner=str(lane), token=token))
    return env


def _parent_lease(path):
    try:
        lease = json.loads(os.environ[_PARENT_LEASE])
        if Path(lease['path']) == path and Path(lease['owner']) == path:
            return lease['token']
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _check_parent(path, token):
    try:
        with _acquire(path, create=False):
            pass
    except DriveBusy as busy:
        if busy.owner.get('token') == token and busy.owner.get('pid') == os.getppid():
            return
    except FileNotFoundError:
        pass
    raise DriveBusy({})


def drive_locks(drives=()):
    """Snapshot available drives and live holders, including holders outside the web service."""
    root = _lock_dir()
    names = {drive_key(drive): drive for drive in drives}
    rows = {key: dict(drive=drive, locked=False, pid=None, action=None) for key, drive in names.items()}
    try:
        paths = list(root.iterdir())
    except FileNotFoundError:
        return list(rows.values())
    for path in sorted(paths):
        key = path.stem
        if not re.fullmatch(r"(?:[A-Z]|[a-f\d]{64})\.lock", path.name) or path.is_symlink():
            continue
        try:
            with _gate(path, create=False):
                continue  # Stale owner bytes after a crash do not count.
        except FileNotFoundError:
            continue
        except DriveBusy as busy:
            owner = busy.owner
            drive = names.get(key) or owner.get("drive") or (key + ":" if len(key) == 1 else key)
            pid = owner.get("pid")
            action = owner.get("action")
            rows[key] = dict(drive=drive, locked=True, pid=pid if type(pid) is int else None,
                             action=action if isinstance(action, str) and action in _ACTIONS else None)
    return list(rows.values())


@contextmanager
def drive_operation(drive, action):
    """Allow nesting within the operation, while independent threads still compete."""
    path = _lock_path(drive)
    held = _held.__dict__.setdefault("paths", {})
    if path in held:
        yield
        return
    parent = _parent_lease(path)
    lane = _lane(path, 'worker') if parent else path
    lock = _acquire(lane) if parent else _gate(path)
    with lock as stream:
        if parent:
            _check_parent(path, parent)
            try:
                with _acquire(_lane(path, 'native'), create=False):
                    pass
            except FileNotFoundError:
                pass
        token = uuid.uuid4().hex
        # Byte zero is locked. Readers can still inspect the owner bytes after it.
        _save_owner(stream, dict(pid=os.getpid(), action=action, drive=os.fspath(drive), token=token))
        held[path] = (lane, token)
        try:
            yield
        finally:
            del held[path]
            stream.truncate(1)


def require_available(drive):
    """Give an immediate refusal before spawning a child. The child still acquires its own lock."""
    path = _lock_path(drive)
    with _gate(path):
        pass


def locked_drive(action):
    def decorate(func):
        @wraps(func)
        def run(drive, *args, **kwargs):
            with drive_operation(drive, action):
                return func(drive, *args, **kwargs)
        return run
    return decorate
