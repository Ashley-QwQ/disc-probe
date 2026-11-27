"""Composable half-open LBA reservations for data measurement.

Producers (disc identity, label layouts, future metadata) feed the same list.
Discovery reads are metadata reads, never random-data measurement samples.
"""
from __future__ import annotations

import math


def exclude_ranges(ranges, reserved, block=16, margin=3000):
    out = list(ranges)
    for lo, hi in reserved:
        lo, hi = lo - margin, hi + margin
        next_ranges = []
        for a, b in out:
            for x, y in ((a, min(b, lo)), (max(a, hi), b)):
                x, y = math.ceil(x/block)*block, y//block*block
                if y > x:
                    next_ranges.append((x, y))
        out = next_ranges
    return out


def nearest(lba, ranges, block, count=1):
    span = math.ceil(count/block)*block
    candidates = [max(a, min(lba//block*block, b-span)) for a,b in ranges if b-a >= span]
    if not candidates:
        raise ValueError('no random-data sample fits outside reserved LBA ranges')
    return min(candidates, key=lambda x: (abs(x-lba), x))
