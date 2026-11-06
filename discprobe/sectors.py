"""Merge Sectors, the third game for the wait: equal blocks slide together and double, from one 2 kB sector up.

It runs as snake does, see `snake.py`: no thread, only inside the random pause before a timed read,
its own random generator, only changed cells drawn. Its board carries over to the next wait: the
file is read when the game first opens and written when the progress line closes, never between reads.
"""

from __future__ import annotations

import json
import math
import os
import random

SIZE = 4
TWO_KB_SHARE = 0.9      # the rest of the new blocks are 4 kB
MAX_TILE = 17           # no 4 by 4 board can go higher
DIRECTION = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def state_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "disc-probe", "games.json")


def label(tile: int) -> str:
    """A tile holds its power of two in kB: 1 is 2K, 15 is 32M."""
    kb = 2 ** tile
    return f"{kb}K" if kb < 1024 else f"{kb // 1024}M"


def merged(line: list[int]) -> tuple[list[int], int]:
    """One row moved towards its start: (the new row, kB gained). A tile merges once per move."""
    tiles = [t for t in line if t]
    out, gained, i = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] + 1)
            gained += 2 ** (tiles[i] + 1)
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(line) - len(out)), gained


class Sectors:
    name = "Merge Sectors"
    min_cols = max_cols = SIZE
    cell_w, cell_h = 7, 2
    step_s = math.inf

    def __init__(self, cols: int = SIZE, rows: int = SIZE, rng=None, path: str | None = None):
        self.cols, self.rows = SIZE, SIZE
        self.rng = rng or random.Random()
        self.path = path or state_path()
        self.best = 0
        self.changed = False
        self.reset()
        self.changed = False
        self._load()

    def reset(self) -> None:
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.score = 0
        self.over = False
        self.changed = True
        self._drop()
        self._drop()

    def hint(self) -> str:
        if self.over:
            return f"Merge Sectors {self.score}  best {self.best}  no room left: r plays again, n next, q closes"
        return f"Merge Sectors {self.score}  best {self.best}  arrows slide, kept for next time, n next, q closes"

    def _drop(self) -> None:
        free = [(x, y) for y in range(SIZE) for x in range(SIZE) if not self.board[y][x]]
        if free:
            x, y = self.rng.choice(free)
            self.board[y][x] = 1 if self.rng.random() < TWO_KB_SHARE else 2

    def _stuck(self) -> bool:
        b = self.board
        return all(b[y][x] and (x == SIZE - 1 or b[y][x] != b[y][x + 1]) and (y == SIZE - 1 or b[y][x] != b[y + 1][x])
                   for y in range(SIZE) for x in range(SIZE))

    def _slide(self, name: str) -> None:
        dx, dy = DIRECTION[name]
        before = [row[:] for row in self.board]
        gained = 0
        for i in range(SIZE):
            # Each row or column, read from the side it moves towards.
            cells = [(i, j) if dx == 0 else (j, i) for j in (range(SIZE) if dx + dy < 0 else range(SIZE - 1, -1, -1))]
            line, got = merged([self.board[y][x] for x, y in cells])
            gained += got
            for (x, y), tile in zip(cells, line):
                self.board[y][x] = tile
        if self.board == before:
            return
        self.score += gained
        self.best = max(self.best, self.score)
        self.changed = True
        self._drop()
        if self._stuck():
            self.over = True

    def step(self) -> list:
        return []

    def turn(self, name: str) -> list[tuple[int, int, str]]:
        if self.over:
            return []
        before = {(x, y): self.cell(x, y) for x in range(SIZE) for y in range(SIZE)}
        self._slide(name)
        return [(x, y, self.cell(x, y)) for (x, y), kind in before.items() if self.cell(x, y) != kind]

    def cell(self, x: int, y: int) -> str:
        return f"tile{self.board[y][x]}"

    def tint(self, x: int, y: int) -> int:
        return 0

    def _load(self) -> None:
        """Whatever is wrong with the file, the game just starts afresh."""
        try:
            with open(self.path, encoding="utf-8") as f:
                state = json.load(f)["sectors"]
            board, score, best = state["board"], state["score"], state["best"]
            valid = (len(board) == SIZE and all(len(row) == SIZE for row in board)
                     and all(type(t) is int and 0 <= t <= MAX_TILE for row in board for t in row)
                     and type(score) is int and type(best) is int and 0 <= score <= best)
        except (OSError, ValueError, KeyError, TypeError):
            return
        if valid:
            self.board, self.score, self.best = board, score, best
            self.over = self._stuck()

    def save(self) -> None:
        if not self.changed:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump({"sectors": {"board": self.board, "score": self.score, "best": self.best}}, f)
            os.replace(temporary, self.path)
            self.changed = False
        except OSError:
            pass        # a game is never worth stopping for
