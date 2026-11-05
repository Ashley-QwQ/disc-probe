"""Make a DVD picture ISO readable: put a guard byte before each run of 92 (experimental).

On the disc, a run of 92 can lock into the code word 0100000000010000, whose DC adds up to about
316 in one sync frame, and some drives then report 3/11/05 (DiscImageStudio #90). After 75 or 9B a
following 92 can only use the zero-DC code word. This rewrites the first 92 of each run, in the
scrambled domain, and leaves the rest alone.

Only sectors that are at least --min-pattern 92 or A5 on the disc are touched, so file system and
data sectors stay as they are. The image must start at LBA 0.

    python tools/bridge_iso.py target.iso target_bridged.iso --check 20

This does not fix everything. A block with no 92 runs can still be high because of its PO rows (all
A5 reaches 325), and --check shows those. Tested on one block on a real drive so far (bczhc, #90: it
read after this change). Whether a whole disc reads, and whether the picture changes, is not known.
"""
import argparse
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsv_block as D  # noqa: E402
from discprobe import dvd  # noqa: E402

BLOCK = dvd.BLOCK_SECTORS * dvd.SECTOR_BYTES


def bridge_sector(rec, guard):
    """First 92 of each run becomes the guard byte. A sector start counts as a new run."""
    first = (rec == 0x92) & (np.r_[False, rec[:-1] == 0x92] == 0)
    out = rec.copy()
    out[first] = guard
    return out, int(first.sum())


def bridge_block(payload, lba, guard, min_pattern):
    out, changed, touched = payload.copy(), 0, 0
    for s in range(dvd.BLOCK_SECTORS):
        a = s * dvd.SECTOR_BYTES
        rec = dvd.recorded(payload[a:a + dvd.SECTOR_BYTES], lba + s)
        if np.mean((rec == 0x92) | (rec == 0xA5)) < min_pattern:
            continue
        new, n = bridge_sector(rec, guard)
        out[a:a + dvd.SECTOR_BYTES] = dvd.recorded(new, lba + s)
        changed += n
        touched += 1
    return out, changed, touched


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--guard", default="9B", choices=("9B", "75"), help="byte placed before each run of 92")
    ap.add_argument("--min-pattern", type=float, default=0.99, help="share of 92 and A5 that marks a sector as picture")
    ap.add_argument("--check", type=int, default=0, help="compare peak |DSV| before and after on this many changed blocks")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if os.path.exists(args.output):
        sys.exit(f"{args.output} exists; not overwriting")
    if os.path.getsize(args.input) % dvd.SECTOR_BYTES:
        sys.exit("input is not a whole number of 2048-byte sectors")
    guard = int(args.guard, 16)
    total = changed = touched = blocks = 0
    picked = []
    rng = np.random.default_rng(args.seed)
    h_in, h_out = hashlib.sha256(), hashlib.sha256()
    with open(args.input, "rb") as fi, open(args.output, "xb") as fo:
        lba = 0
        while True:
            raw = fi.read(BLOCK)
            if not raw:
                break
            h_in.update(raw)
            data = np.frombuffer(raw, np.uint8)
            if len(raw) == BLOCK and lba % dvd.BLOCK_SECTORS == 0:
                out, c, t = bridge_block(data, lba, guard, args.min_pattern)
            else:
                out, c, t = data, 0, 0   # a short block at the end of the image
            fo.write(out.tobytes())
            h_out.update(out.tobytes())
            total += len(raw) // dvd.SECTOR_BYTES
            changed += c
            touched += t
            if c:
                blocks += 1
                # reservoir sample, so the check is spread over the disc
                if len(picked) < args.check:
                    picked.append((lba, raw, out.tobytes()))
                elif args.check and rng.integers(blocks) < args.check:
                    picked[rng.integers(args.check)] = (lba, raw, out.tobytes())
            lba += len(raw) // dvd.SECTOR_BYTES
    print(f"{total} sectors; {touched} treated as picture, {changed} bytes changed "
          f"({100 * changed / max(1, touched * dvd.SECTOR_BYTES):.2f} % of those sectors), guard {args.guard}")
    print(f"sha256 in  {h_in.hexdigest()}\nsha256 out {h_out.hexdigest()}")
    if picked:
        print("peak |DSV| on sampled blocks, before and after (model only; random data is about 29):")
        worst = 0
        for lba, a, b in sorted(picked, key=lambda x: x[0]):
            before = D.report(np.frombuffer(a, np.uint8), lba)[0]
            after = D.report(np.frombuffer(b, np.uint8), lba)[0]
            worst = max(worst, after)
            print(f"  LBA {lba:8d}: {before:4d} -> {after:4d}")
        print(f"worst after: {worst}" + ("  (high: probably PO rows, see the note at the top of this file)" if worst > 100 else ""))


if __name__ == "__main__":
    main()
