"""Sudoku for the wait, sized to it: 4x4 for a short one, 6x6 for a longer one.

It runs as snake does, see `snake.py`: no thread, only inside the random pause before a timed read,
its own random generator, only changed cells drawn. A puzzle has exactly one solution. It comes from
a solved grid, whose rows, columns and digits are shuffled in ways that keep it solved, with cells
taken out for as long as the answer stays unique, so opening one needs no long search.
"""

from __future__ import annotations

import math
import random

SHORT_WAIT_S = 30.0     # below this a puzzle would not get finished
LONG_WAIT_S = 120.0


def _shuffled_groups(rng, count: int, size: int) -> list[int]:
    """0..count*size-1 with the groups of `size` shuffled, and the order inside each."""
    groups = rng.sample(range(count), count)
    return [g * size + i for g in groups for i in rng.sample(range(size), size)]


def solved_grid(rng, box_h: int, box_w: int) -> list[list[int]]:
    size = box_h * box_w
    rows = _shuffled_groups(rng, box_w, box_h)
    cols = _shuffled_groups(rng, box_h, box_w)
    digits = rng.sample(range(1, size + 1), size)
    return [[digits[(box_w * (r % box_h) + r // box_h + c) % size] for c in cols] for r in rows]


def count_solutions(grid: list[list[int]], box_h: int, box_w: int, limit: int = 2) -> int:
    """Solutions up to `limit`, always trying the cell with the fewest digits left."""
    size = box_h * box_w
    grid = [row[:] for row in grid]

    def options(r: int, c: int) -> list[int]:
        used = set(grid[r]) | {grid[i][c] for i in range(size)}
        top, left = r - r % box_h, c - c % box_w
        used |= {grid[i][j] for i in range(top, top + box_h) for j in range(left, left + box_w)}
        return [d for d in range(1, size + 1) if d not in used]

    def search() -> int:
        best = None
        for r in range(size):
            for c in range(size):
                if not grid[r][c]:
                    found = options(r, c)
                    if best is None or len(found) < len(best[2]):
                        best = (r, c, found)
        if best is None:
            return 1
        r, c, found = best
        total = 0
        for d in found:
            grid[r][c] = d
            total += search()
            if total >= limit:
                break
        grid[r][c] = 0
        return total
    return search()


class Sudoku:
    box_h = box_w = 2
    givens = 6
    min_cols = max_cols = 4
    cell_w, cell_h = 6, 2
    step_s = math.inf

    def __init__(self, cols: int = 0, rows: int = 0, rng=None):
        self.size = self.box_h * self.box_w
        self.cols = self.rows = self.size
        self.rng = rng or random.Random()
        self.keys = (*(str(d) for d in range(1, self.size + 1)), "0", " ")
        self.name = f"Sudoku {self.size}x{self.size}"
        self.best = 0
        self.score = 0
        self.reset()

    def reset(self) -> None:
        """Another puzzle; the count of solved ones carries on."""
        self.solution = solved_grid(self.rng, self.box_h, self.box_w)
        self.grid = [row[:] for row in self.solution]
        left = self.size ** 2
        for r, c in self.rng.sample([(r, c) for r in range(self.size) for c in range(self.size)], self.size ** 2):
            if left <= self.givens:
                break
            kept, self.grid[r][c] = self.grid[r][c], 0
            if count_solutions(self.grid, self.box_h, self.box_w) != 1:
                self.grid[r][c] = kept
            else:
                left -= 1
        self.given = {(c, r) for r in range(self.size) for c in range(self.size) if self.grid[r][c]}
        self.over = False
        self.x, self.y = next((c, r) for r in range(self.size) for c in range(self.size) if not self.grid[r][c])

    def hint(self) -> str:
        if self.over:
            return f"{self.name}  solved {self.score}  all correct: r for another, n next, q closes"
        return f"{self.name}  solved {self.score}  arrows move, 1-{self.size} fill, 0 clears, n next, q closes"

    def _wrong(self, x: int, y: int) -> bool:
        digit = self.grid[y][x]
        if not digit:
            return False
        top, left = y - y % self.box_h, x - x % self.box_w
        peers = [(c, y) for c in range(self.size)] + [(x, r) for r in range(self.size)] + \
                [(c, r) for r in range(top, top + self.box_h) for c in range(left, left + self.box_w)]
        return any((c, r) != (x, y) and self.grid[r][c] == digit for c, r in peers)

    def step(self) -> list:
        return []

    def _press(self, name: str) -> None:
        moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        if name in moves:
            self.x = (self.x + moves[name][0]) % self.size
            self.y = (self.y + moves[name][1]) % self.size
        elif (self.x, self.y) not in self.given:
            self.grid[self.y][self.x] = int(name) if name.isdigit() else 0
            if self.grid == self.solution:
                self.over = True
                self.score += 1
                self.best = max(self.best, self.score)

    def turn(self, name: str) -> list[tuple]:
        if self.over:
            return []
        before = {(x, y): self.cell(x, y) for x in range(self.size) for y in range(self.size)}
        self._press(name)
        return [(x, y, self.cell(x, y)) for (x, y), kind in before.items() if self.cell(x, y) != kind]

    def cell(self, x: int, y: int) -> tuple:
        state = "solved" if self.over else "given" if (x, y) in self.given else "wrong" if self._wrong(x, y) else "mine"
        return ("sudoku", self.grid[y][x], state, (x, y) == (self.x, self.y) and not self.over, self.tint(x, y), self.cell_w, self.cell_h)

    def tint(self, x: int, y: int) -> int:
        return (x // self.box_w + y // self.box_h) % 2


class Sudoku4(Sudoku):
    pass


class Sudoku6(Sudoku):
    box_h, box_w = 2, 3     # six cells split evenly: two rows of three
    givens = 14
    min_cols = max_cols = 6
    cell_w, cell_h = 4, 1


def for_wait(seconds: float | None):
    """The puzzle for a wait of this length, or None where there is not time for one."""
    if seconds is None or seconds < SHORT_WAIT_S:
        return None
    return Sudoku4 if seconds < LONG_WAIT_S else Sudoku6
