"""Score the offline trouble search corpus and measure lookup latency."""
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "tests/data/troubleshoot_queries.jsonl"


def load_queries():
    return [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines()]


def score(queries, search):
    total, hits, first = Counter(), Counter(), Counter()
    missed, elapsed = [], []
    for case in queries:
        kind = case["kind"]
        start = perf_counter()
        results = search(case["query"])["results"]
        elapsed.append((perf_counter() - start) * 1000)
        ids = [result["id"] for result in results
               if kind != "error" or result["match"] == "error"]
        total[kind] += 1
        first[kind] += bool(ids and ids[0] == case["expected"])
        if case["expected"] in ids:
            hits[kind] += 1
        else:
            missed.append(dict(case=case["case"], expected=case["expected"], returned=ids))
    return dict(total=dict(total), hits=dict(hits), first=dict(first),
                misses=missed, cold_ms=round(elapsed[0], 3),
                warm_median_ms=round(median(elapsed[1:]), 3), warm_max_ms=round(max(elapsed[1:]), 3))


def passing(result):
    total, hits = result["total"], result["hits"]
    return (sum(total.values()) >= 50 and total.get("error", 0) > 0 and total.get("symptom", 0) > 0
            and hits.get("error") == total["error"]
            and sum(hits.values()) / sum(total.values()) >= 0.90)


def main():
    sys.path.insert(0, str(ROOT))
    from discprobe.troubleshoot import search

    result = score(load_queries(), search)
    print(json.dumps(result, indent=2))
    return 0 if passing(result) else 1


if __name__ == "__main__":
    sys.exit(main())
