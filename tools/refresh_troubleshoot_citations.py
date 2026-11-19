"""Move each troubleshooting citation's line number to where its keyword now is.

Citations name a file, a line and a keyword that must appear on that line
(tests/test_troubleshoot.py checks it). Code moves; the keyword does not. Run this
after a merge that shifts lines:

    python tools/refresh_troubleshoot_citations.py [--check]

A citation is moved only when its keyword occurs on exactly one line of the file, or,
when it occurs on several, to the occurrence nearest the old line. A keyword that no
longer occurs anywhere is reported and left alone: that entry needs a person.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "discprobe" / "data" / "troubleshoot.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; exit 1 if anything would change")
    args = parser.parse_args(argv)
    raw = DATA.read_bytes().decode("utf-8")
    entries = json.loads(raw)
    cache, moved, missing = {}, [], []
    for entry in entries:
        for source in entry.get("sources", []):
            if not {"path", "line", "keyword"} <= set(source):
                continue
            lines = cache.setdefault(source["path"], (ROOT / source["path"]).read_text(encoding="utf-8-sig").splitlines())
            line, keyword = source["line"], source["keyword"]
            if 1 <= line <= len(lines) and keyword in lines[line - 1]:
                continue
            hits = [i + 1 for i, text in enumerate(lines) if keyword in text]
            if not hits:
                missing.append((entry["id"], source["path"], line, keyword))
                continue
            new = min(hits, key=lambda n: abs(n - line))
            moved.append((entry["id"], source["path"], line, new))
            source["line"] = new
    for item in moved:
        print("moved   %s %s:%d -> %d" % item)
    for item in missing:
        print("MISSING %s %s:%d %r" % item)
    if moved and not args.check:
        # The file is laid out by hand: change only the numbers, never re-serialise it.
        for entry_id, path, old, new in moved:
            keyword = next(s["keyword"] for e in entries if e["id"] == entry_id for s in e["sources"]
                           if s.get("path") == path and s.get("line") == new)
            quoted = json.dumps(keyword, ensure_ascii=False)
            stale, fresh = f'"line": {old}, "keyword": {quoted}', f'"line": {new}, "keyword": {quoted}'
            if raw.count(stale) != 1:
                raise SystemExit(f"cannot place {entry_id} {path}:{old} uniquely; edit it by hand")
            raw = raw.replace(stale, fresh)
        DATA.write_bytes(raw.encode("utf-8"))
    return 1 if missing or (args.check and moved) else 0


if __name__ == "__main__":
    raise SystemExit(main())
