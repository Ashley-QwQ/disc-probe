"""The lab folder: public box label, the secret answer file, and the drive/tray/burn state.

    LAB/box.json        what is printed on the box (media, batch, disc labels): disc-probe may see this
    LAB/answers.json    every true parameter; only disclab reads it
    LAB/state.json      drives, which disc is in which tray, what was burned on each disc
    LAB/results/        disc-probe --out
    LAB/iso/, LAB/photos/, LAB/scores/
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import time

ENV = "DISCPROBE_DISCLAB"


def atomic_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=float) + "\n", encoding="utf-8")
    for attempt in range(50):
        try:
            tmp.replace(path)
            return
        except PermissionError:      # Windows: a reader has it open for a moment
            time.sleep(0.05)
    tmp.replace(path)


class Lab:
    def __init__(self, root):
        self.root = Path(root).resolve()

    @classmethod
    def from_env(cls):
        root = os.environ.get(ENV)
        return cls(root) if root else None

    # ------------------------------------------------------------ files
    @property
    def box_path(self):
        return self.root / "box.json"

    @property
    def answers_path(self):
        return self.root / "answers.json"

    @property
    def state_path(self):
        return self.root / "state.json"

    def read(self, path):
        for attempt in range(50):
            try:
                return json.loads(Path(path).read_text(encoding="utf-8"))
            except (PermissionError, json.JSONDecodeError):
                time.sleep(0.05)
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def box(self):
        return self.read(self.box_path)

    def answers(self):
        return self.read(self.answers_path)

    def state(self):
        if not self.state_path.exists():
            return {"drives": {}, "burns": {}, "events": [], "steps": {}}
        return self.read(self.state_path)

    @contextlib.contextmanager
    def locked_state(self):
        """Read-modify-write of state.json under a lock file (several disc-probe processes may share a lab)."""
        lock = self.root / ".state.lock"
        deadline = time.time() + 30
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.time() > deadline:
                    try:
                        if time.time() - lock.stat().st_mtime > 60:
                            lock.unlink()
                            continue
                    except FileNotFoundError:
                        continue
                    raise TimeoutError(f"lab state is locked: {lock}")
                time.sleep(0.05)
        try:
            state = self.state()
            yield state
            atomic_json(self.state_path, state)
        finally:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()

    def event(self, state, kind, **fields):
        record = dict(t=round(time.time(), 3), kind=kind, **fields)
        state.setdefault("events", []).append(record)
        paths = [str(self.box_path), str(self.answers_path)] if kind == "box" else []
        if fields.get("iso"):
            paths.append(fields["iso"])
        state.setdefault("steps", {}).setdefault(kind, []).append(
            dict(record, status="ok", paths=paths))

    def step(self, kind, **fields):
        """Append progress without replacing drive, burn, event or extension keys."""
        fields.setdefault("paths", fields.get("outputs", {}).get("paths", [str(self.state_path)]))
        with self.locked_state() as state:
            state.setdefault("steps", {}).setdefault(kind, []).append(
                dict(t=round(time.time(), 3), **fields))

    # ------------------------------------------------------------ lookups
    def drive_for(self, name: str):
        """(drive state, reader truth) for a drive name such as 'X:', or None if this lab has no such drive."""
        name = name.rstrip("\\/").upper()
        if not name.endswith(":"):
            name += ":"
        st = self.state()
        d = st.get("drives", {}).get(name)
        if d is None:
            return None
        return name, d

    def disc_truth(self, disc_id: str) -> dict:
        return self.answers()["discs"][disc_id]

    def reader_truth(self, profile: str) -> dict:
        return self.answers()["readers"][profile]

    def writer_truth(self, profile: str) -> dict:
        return self.answers()["writers"][profile]
