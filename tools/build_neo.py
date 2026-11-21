"""Assemble the Disc Neo data-pack staging folder from the running texture atlas.

    python -B tools/build_neo.py                      # full rebuild with the latest atlas data
    python -B tools/build_neo.py --reuse-export       # docs/CSV only, reuse the last export
    python -B tools/build_neo.py --check-only         # run the packaging checks on --out
    python -B tools/build_neo.py --snapshot DIR --atlas-code DIR --extra

Frozen mode bypasses steps 1-4 below. It verifies SHA256SUMS, streams the daily
journal, and copies the official export unchanged. Explicit --extra folders opt
into a merge only after a daily-only replay matches the official export exactly.

Read-only towards the campaign. It never writes inside the atlas worktree and never
starts, stops or signals a worker. Python files under evidence/atlas define the
campaign's code_version, so nothing is created there (imports run with -B semantics).

Export path, step by step (mirrors evidence.atlas.campaign.coordinate):
  1. Copy the coordinator's inputs (ready manifest, collected shard and refine journals,
     plan, control, clock) plus the CPU helper journals (--extra) into --work/src.
     A torn last line is cut in the copy only.
  2. Stream every copy once, re-verify its hash chain with the atlas digest and index the
     byte offset of each target's latest event (canonical IDs, as Journal does).
  3. Merge targets in memory-bounded groups with the atlas's own combined_targets, apply
     the rolling refine-input revision rule (Journal.append) and the reference-stale rule,
     keep ring-progress inputs, and drop the bulky search state merge() never reads
     (runs, GPU top lists, seeds, options, proofs).
  4. Write one compacted snapshot journal and call the atlas's own merge() on it.
  5. Build CSV indexes, docs, PROVENANCE.json, LICENSE and texture-cards/ (git archive),
     then swap the new folder into --out and run the release.py packaging checks.
"""
import argparse
import csv
import ctypes
import datetime as dt
import gc
import hashlib
import io
import math
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time
from collections import Counter

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / 'tools' / 'neo_templates'
DEFAULT_ATLAS = Path('D:/disc-probe/.claude/worktrees/atlas-core')
DEFAULT_OUT = Path('C:/disc-probe-scratch/disc-neo')
DEFAULT_WORK = Path('D:/disc-probe-scratch/disc-neo-work')  # C: filled up on 11-13; work data lives on D:
# CPU helper workers (from 11-14 13:10) search coarse targets left on the glassbox and x79 shards with the unchanged
# budget_worker --device cpu; same manifest schema, same seeds, invisible to the GPU workers and the coordinator.
DEFAULT_EXTRA = (Path('D:/disc-probe-scratch/atlas-extra/collected'),)
# The CPU helper shards of plan.extra.json. Any other journal in an --extra folder is an extra GPU process
# (e.g. glassbox2, a second GPU worker on glassbox from 11-14 19:19, plan.rebal.json with unchanged job contents).
CPU_HELPERS = ('x1280p-a', 'x1280p-b', 'x1280p-c', 'xlocal-a', 'xlocal-b', 'xglass-a', 'xglass-b')
NEO_REQUIRED = ('README.md', 'README.zh.md', 'SCHEMA.md', 'PROVENANCE.json', 'LICENSE')
HEAVY = ('runs', 'top', 'seeds', 'options', 'prior_domain_runs', 'proofs')
REFINE_HOSTS = ('x79', 'lab1280p')
VERSION = '1.0.0.0-alpha'


def allowed(path):
    return all('b' + 'lind' not in p.casefold() for p in Path(path).parts)


def log(*args):
    print(time.strftime('%H:%M:%S'), *args, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def available_mb():
    if os.name != 'nt':
        with open('/proc/meminfo') as f:
            info = dict(line.split(':', 1) for line in f)
        return int(info['MemAvailable'].split()[0]) // 1024
    class Status(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    s = Status(); s.dwLength = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.ullAvailPhys // 2**20


class Guard:
    """Abort before this process squeezes the campaign workers out of RAM.

    A daemon thread also watches free RAM during the long merge() call and exits
    this process at once if the floor is crossed; it never touches other processes."""
    def __init__(self, floor_mb):
        self.floor = floor_mb
        self.peak_bytes = 0
        self.samples = 0
        self.sample()
        import threading
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while True:
            time.sleep(5)
            self.sample()
            free = available_mb()
            if free < self.floor:
                self.stop(f'RAM watchdog: {free} MB free, below {self.floor} MB')

    def stop(self, reason):
        if getattr(self, 'report_path', None):
            self.report_path.write_text(json.dumps(dict(status='FAIL', error=reason,
                peak_working_set_bytes=self.peak_bytes, working_set_sample_seconds=5,
                working_set_samples=self.samples), indent=1), encoding='utf-8')
        print(reason + '; exiting this build only', flush=True)
        os._exit(3)

    def sample(self):
        if os.name == 'nt':
            class Counters(ctypes.Structure):
                _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong),
                            *[(n, ctypes.c_size_t) for n in ('peak_ws', 'ws', 'peak_pool', 'pool',
                                                          'peak_nonpool', 'nonpool', 'page', 'peak_page')]]
            c = Counters(); c.cb = ctypes.sizeof(c)
            kernel = ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
            memory_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            if not memory_info(kernel.GetCurrentProcess(), ctypes.byref(c), c.cb):
                raise ctypes.WinError()
            current, peak = c.ws, c.peak_ws
        else:
            import resource
            current = int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        self.peak_bytes = max(self.peak_bytes, peak, current)
        self.samples += 1
        if self.peak_bytes > 4 * 2**30:
            self.stop('working set exceeded 4 GiB')
        return current

    def check(self, where):
        self.sample()
        free = available_mb()
        if free < self.floor:
            raise SystemExit(f'stopped at {where}: only {free} MB RAM available (floor {self.floor} MB); '
                             'nothing in the campaign was touched. Retry later or lower --group-mb.')
        return free


def low_priority():
    if os.name == 'nt':
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        if not k.SetPriorityClass(k.GetCurrentProcess(), 0x4000):  # BELOW_NORMAL_PRIORITY_CLASS
            raise ctypes.WinError()
    else:
        os.nice(10)


# --------------------------------------------------------------------------- snapshot

def cut_torn_tail(path):
    """repair_tail semantics, applied to our private copy only."""
    size = path.stat().st_size
    if not size:
        return None
    with open(path, 'rb') as f:
        f.seek(max(0, size - (8 << 20)))
        tail = f.read()
    if tail.endswith(b'\n'):
        return None
    stop = tail.rfind(b'\n')
    start = size - len(tail) + stop + 1
    with open(path, 'rb') as f:
        f.seek(start); fragment = f.read()
    try:
        json.loads(fragment)
    except ValueError:
        with open(path, 'r+b') as f:
            f.truncate(start)
        return f'cut {len(fragment)} torn bytes'
    with open(path, 'ab') as f:
        f.write(b'\n')
    return 'restored final newline'


def chain_ok(path, A):
    tail, seq = '0' * 64, 0
    try:
        with open(path, 'rb') as f:
            for raw in f:
                event = json.loads(raw)
                seal = event.pop('event_hash')
                if event['previous_hash'] != tail or A.digest(event) != seal or event['sequence'] != seq:
                    return None
                tail, seq = seal, seq + 1
    except (ValueError, KeyError):
        return None
    return seq


def fetch_remote(host, epoch, name, dest, timeout, A, attempts=3):
    """Read-only copy of a GPU worker's own journal, for when the coordinator's copy is stale.

    Tries a gzip stream over ssh first (Linux workers; about 5x less traffic), then plain scp."""
    import gzip
    rel = f'dp-search/atlas-core-{epoch}/evidence/atlas/run-{name}/manifest.jsonl'
    part, packed = dest.with_name(dest.name + '.part'), dest.with_name(dest.name + '.part.gz')
    ssh = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=30', '-o', 'ServerAliveInterval=15']
    started = time.time()
    for attempt in range(1, attempts + 1):
        for method in ('ssh-gzip', 'scp'):
            part.unlink(missing_ok=True); packed.unlink(missing_ok=True)
            try:
                if method == 'ssh-gzip':
                    with open(packed, 'wb') as out:
                        r = subprocess.run(['ssh', *ssh, host, f'gzip -1 -c {rel}'], stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=subprocess.PIPE, timeout=timeout)
                    if r.returncode == 0:
                        with gzip.open(packed, 'rb') as src, open(part, 'wb') as out:
                            shutil.copyfileobj(src, out, 1 << 20)
                else:
                    r = subprocess.run(['scp', '-q', *ssh, f'{host}:{rel}', str(part)], stdin=subprocess.DEVNULL,
                                       capture_output=True, timeout=timeout)
                ok = r.returncode == 0 and part.exists() and part.stat().st_size > 0
            except (subprocess.TimeoutExpired, OSError, EOFError, gzip.BadGzipFile):
                ok = False
            packed.unlink(missing_ok=True)
            if not ok:
                log(f'fetch attempt {attempt} ({method}) failed for {host}:{rel}')
                continue
            repaired = cut_torn_tail(part)
            events = chain_ok(part, A)
            if events is None:
                log(f'fetched journal failed its hash chain ({method}); ignored')
                continue
            os.replace(part, dest)
            log(f'fetched {host}:{rel} by {method} in {time.time() - started:.0f} s, {events} events')
            return dict(fetched_from=f'{host}:{rel}', method=method,
                        fetched_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                        fetch_seconds=round(time.time() - started), fetch_repair=repaired, events=events)
        time.sleep(20)
    part.unlink(missing_ok=True)
    log(f'giving up on a direct fetch from {host}; using the coordinator copy')
    return None


def helper_journals(extra_dirs):
    """(role, absolute path) for every journal in the extra folders, sorted so the merge order is stable.

    Every *.jsonl is read. Known CPU helpers get role cpu-helper:<name>; any other file is an extra GPU process,
    gpu-extra:<name> (counted with the GPU journals, never fetched remotely)."""
    found = []
    for d in extra_dirs:
        d = Path(d)
        if not allowed(d) or not d.is_dir():
            continue
        found += [(('cpu-helper:' if f.stem in CPU_HELPERS else 'gpu-extra:') + f.stem, f)
                  for f in sorted(d.glob('*.jsonl')) if allowed(f)]
    return found


def snapshot_sources(ev, epoch, src, A=None, stale_minutes=0, fetch_timeout=1800, extra_dirs=()):
    plan = json.loads((ev / 'plan.json').read_text(encoding='utf-8'))
    names = [('manifest', 'manifest.campaign.ready.jsonl')]
    names += [(f'gpu:{n}', f'collected/{epoch}-{n}.jsonl') for n in plan['shards']]
    names += [(f'cpu-refine:{n}', f'collected/refined-{n}.jsonl') for n in REFINE_HOSTS]
    names = [(role, rel, ev / rel, rel.replace('/', '__')) for role, rel in names]
    # Helper journals come after the coordinator's, so every target keeps its coordinator order.
    names += [(role, str(path), path, 'extra__' + path.name) for role, path in helper_journals(extra_dirs)]
    extras = [('plan', 'plan.json'), ('control', f'control-{epoch}.json'), ('clock', f'campaign-{epoch}.json'),
              ('daily-status', 'daily-status.json')]
    extras = [(role, rel, ev / rel, rel.replace('/', '__')) for role, rel in extras]
    if src.exists():
        shutil.rmtree(src)
    src.mkdir(parents=True)
    rows = []
    for role, rel, source, copy_name in names + extras:
        if not source.exists():
            rows.append(dict(role=role, source=rel, present=False)); continue
        mtime = source.stat().st_mtime
        target = src / copy_name
        fetched = None
        name = role.split(':', 1)[1] if role.startswith('gpu:') else None
        if name and name != 'local' and stale_minutes and time.time() - mtime > stale_minutes * 60:
            log(f'{rel} is {(time.time() - mtime) / 60:.0f} min old; fetching the worker journal directly')
            fetched = fetch_remote(name, epoch, name, target, fetch_timeout, A)
        if fetched is None:
            shutil.copyfile(source, target)
        repaired = cut_torn_tail(target) if rel.endswith('.jsonl') and fetched is None else None
        rows.append(dict(role=role, source=rel, present=True, copy=target.name,
                         source_mtime_utc=dt.datetime.fromtimestamp(mtime, dt.timezone.utc).isoformat(timespec='seconds'),
                         bytes=target.stat().st_size, sha256=sha256(target), copy_repair=repaired,
                         **({'replaced_by_direct_fetch': fetched} if fetched else {})))
        log('copied' if fetched is None else 'using fetched', rel, rows[-1]['bytes'] // 2**20, 'MB', repaired or '')
    return rows


# --------------------------------------------------------------------------- indexing

def index_journal(path, A, guard):
    """Verify the chain like Journal._read; keep (first position, latest offset) per canonical id."""
    tail, seq = '0' * 64, 0
    first, latest, sizes = {}, {}, {}
    offset = 0
    with open(path, 'rb') as f:
        for raw in f:
            event = json.loads(raw)
            seal = event.pop('event_hash')
            if event['previous_hash'] != tail or A.digest(event) != seal or event['sequence'] != seq:
                raise ValueError(f'journal hash chain failed: {path} event {seq}')
            tid = A.canonical_target(event['target'])['id']
            first.setdefault(tid, len(first))
            latest[tid] = offset
            sizes[tid] = len(raw)
            tail, seq = seal, seq + 1
            offset += len(raw)
            if seq % 500 == 0:
                guard.check(f'indexing {path.name}')
    return dict(events=seq, first=first, latest=latest, sizes=sizes, tail=tail)


def revision_table(path, A):
    """Rolling refine-input queue state needed to replay Journal.append's revision rule.

    Read live and read-only, up to its last complete line."""
    table, consumed = {}, 0
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for raw in f:
            if not raw.endswith(b'\n'):
                break
            h.update(raw); consumed += len(raw)
            t = A.canonical_target(json.loads(raw)['target'])
            table[t['id']] = dict(rev=t.get('rev', 0), swatch_fingerprint=t.get('swatch_fingerprint'),
                                  verified=t.get('verified', 'none'), id_definition_hash=t['id_definition_hash'])
    return table, dict(bytes_read=consumed, sha256_of_bytes_read=h.hexdigest(), targets=len(table))


class Atlas:
    """Read-only handles into the atlas package of the campaign worktree."""
    def __init__(self, root):
        sys.path.insert(0, str(REPO))  # codec imports discprobe; atlas itself comes from root
        sys.path.insert(0, str(root))
        import evidence.atlas.merge as merge
        import evidence.atlas.journal as journal
        import evidence.atlas.campaign as campaign
        import evidence.atlas.provenance as provenance
        from evidence.atlas.codecs import dvd
        from evidence.atlas.identity import canonical_target
        from evidence.atlas.metrics import rank
        from evidence.atlas.targets import digest
        self.merge, self.journal, self.campaign, self.provenance, self.dvd = merge, journal, campaign, provenance, dvd
        self.canonical_target, self.rank, self.digest = canonical_target, rank, digest
        self.module_root = Path(merge.__file__).resolve().parent
        if self.module_root != (root / 'evidence' / 'atlas').resolve():
            raise RuntimeError(f'imported the wrong atlas package: {self.module_root}')


def make_filtered_journal(indexes, group):
    class FilteredJournal:
        """Journal(path).latest restricted to one group, same insertion order."""
        def __init__(self, path):
            info = indexes[str(path)]
            self.latest = {}
            ids = sorted((tid for tid in group if tid in info['latest']), key=info['first'].__getitem__)
            with open(path, 'rb') as f:
                for tid in ids:
                    f.seek(info['latest'][tid])
                    event = json.loads(f.readline())
                    t = FilteredJournal.A.canonical_target(event['target'])
                    assert t['id'] == tid
                    self.latest[tid] = t
    return FilteredJournal


def apply_queue_revision(A, t, previous):
    """Journal.append's revision rule against the rolling refine-input queue."""
    target = A.canonical_target(t)
    if previous and previous['id_definition_hash'] != target['id_definition_hash']:
        raise ValueError('permanent ID collision: ' + target['id'])
    full = target.get('refined_top', [])
    winner = max(full, key=lambda c: A.rank(target, c)) if full else None
    if winner:
        fingerprint = A.digest([winner['spec'], winner['periods_T']])
        prior = previous.get('swatch_fingerprint') if previous else None
        target['rev'] = (previous.get('rev', 0) if previous else target.get('rev', 0)) + (fingerprint != prior)
        target.update(swatch_fingerprint=fingerprint, swatch_spec=winner['spec'])
        if fingerprint != prior:
            target['verified'] = 'none'
    return target


RISK_CODES = ('low (A5-like)', 'low F512, frames lean', 'as 92', 'HIGH')


def safe_rank(A, t, c):
    try:
        return A.rank(t, c)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def candidate_entry(A, t, c, whole, sources, T_um):
    m = c.get('metrics') or {}
    risk = m.get('risk')
    if risk is None and m.get('proxy_risk_code') is not None:
        try:
            risk = RISK_CODES[int(m['proxy_risk_code'])]
        except (ValueError, IndexError, TypeError):
            risk = None
    periods = c.get('periods_T') or []
    shares = t.get('shares') or []
    main = periods[max(range(len(shares)), key=shares.__getitem__)] if periods and len(shares) == len(periods) else (periods[0] if periods else None)
    r = safe_rank(A, t, c)
    objective = r[0] if r and isinstance(r[0], (int, float)) and r[0] > -1e29 else None
    leakage = m.get('leakage') or {}
    return dict(spec=c['spec'], k=c.get('k'), basis='whole-block' if whole else 'gpu-proxy',
                measurement=c.get('measurement', 'UNKNOWN'), purity_basis=m.get('purity_basis'),
                periods_T=periods, periods_um=[p * T_um for p in periods],
                main_period_um=main * T_um if main is not None else None,
                purity=m.get('purity'), objective=objective,
                leakage_max=max(leakage.values()) if leakage else None,
                F512_percent=m.get('F512_percent') if whole else None, F1488_percent=m.get('F1488_percent') if whole else None,
                lean=m.get('lean') if whole else None, peak_DSV=m.get('peak_DSV') if whole else None,
                risk=risk or 'UNKNOWN', risk_basis=(m.get('risk_basis') or 'model thresholds') if whole else 'gpu proxy risk code',
                proxy_score=c.get('proxy_score'), sources=sorted(sources))


def ranked_candidates(A, t, T_um):
    """Every distinct spec seen for this target, ranked.

    Whole-block CPU measurements come first, ordered by the atlas's own rank() (the rule that
    picks the published winner, so rank 1 is the winner). Specs seen only as GPU approximations
    follow, ordered by the same rank() on their proxy metrics, then by proxy score."""
    found = []
    for c in t.get('refined_top', []):
        found.append((c, 'refined_top'))
    for c in t.get('refined_candidates', []):
        found.append((c, 'refined_candidates'))
    for c in t.get('top', []):
        found.append((c, 'top'))
    for r in t.get('runs', []):
        for c in r.get('top', []) or []:
            found.append((c, f"run{r.get('run_index')}.top"))
        for c in r.get('refined_top', []) or []:
            found.append((c, f"run{r.get('run_index')}.refined_top"))
    best, sources = {}, {}
    for c, src in found:
        if not c.get('spec'):
            continue
        spec = c['spec'].upper()
        whole = c.get('measurement') == 'whole' and (c.get('metrics') or {}).get('purity') is not None
        sources.setdefault(spec, set()).add(src)
        old = best.get(spec)
        if old is None or (whole and not old[1]):
            best[spec] = (c, whole); continue
        if whole == old[1]:
            a, b = safe_rank(A, t, c), safe_rank(A, t, old[0])
            if a is not None and (b is None or a > b):
                best[spec] = (c, whole)
    whole = [v[0] for v in best.values() if v[1]]
    proxy = [v[0] for v in best.values() if not v[1]]
    whole.sort(key=lambda c: safe_rank(A, t, c) or (-math.inf,), reverse=True)
    proxy.sort(key=lambda c: (safe_rank(A, t, c) or (-math.inf,), c.get('proxy_score') or -math.inf), reverse=True)
    rows = []
    for i, c in enumerate(whole + proxy, 1):
        e = candidate_entry(A, t, c, i <= len(whole), sources[c['spec'].upper()], T_um)
        e['rank'] = i
        rows.append(e)
    return rows


def light_runs(runs):
    return [dict(complete=bool(r.get('complete')),
                 refine_complete=bool(r.get('refine_complete') or r.get('refined_top') or r.get('refined_candidates')))
            for r in runs]


def export_atlas(args, A, guard, work, sources):
    ev = args.atlas / 'evidence' / 'atlas'
    src = work / 'src'
    journals = [src / r['copy'] for r in sources if r['present'] and r['copy'].endswith('.jsonl')]
    roles = {r['copy']: r['role'] for r in sources if r['present']}
    indexes = {}
    for path in journals:
        log('indexing', path.name)
        indexes[str(path)] = index_journal(path, A, guard)
    # Global target order == combined_targets' dict insertion order over the input list.
    order = {}
    for i, path in enumerate(journals):
        info = indexes[str(path)]
        for tid, pos in info['first'].items():
            order.setdefault(tid, (i, pos))
    weight = {tid: sum(indexes[str(p)]['sizes'].get(tid, 0) for p in journals) for tid in order}
    groups, current, size = [], [], 0
    for tid in sorted(order, key=order.__getitem__):
        if current and size + weight[tid] > args.group_mb * 2**20:
            groups.append(current); current, size = [], 0
        current.append(tid); size += weight[tid]
    if current:
        groups.append(current)
    log(f'{len(order)} targets in {len(groups)} merge groups')

    queue_path = ev / 'refine-input.jsonl'
    log('reading refine-input revision state (live, read-only)')
    revisions, queue_info = revision_table(queue_path, A)
    control = json.loads((src / f'control-{args.epoch}.json').read_text(encoding='utf-8'))
    plan = json.loads((src / 'plan.json').read_text(encoding='utf-8'))

    parts, light, stale = [], {}, 0
    real_journal = A.merge.Journal
    cand = open(work / 'candidates.jsonl.tmp', 'w', encoding='utf-8', newline=chr(10))
    try:
        for g, ids in enumerate(groups):
            guard.check(f'merge group {g}')
            Filtered = make_filtered_journal(indexes, set(ids))
            Filtered.A = A
            A.merge.Journal = Filtered
            merged = A.merge.combined_targets(journals)
            A.merge.Journal = real_journal
            part = work / f'part-{g:03d}.jsonl'
            with open(part, 'w', encoding='utf-8', newline='\n') as f:
                for t in merged:
                    t = apply_queue_revision(A, t, revisions.get(t['id']))
                    if not t.get('retired'):
                        cand.write(json.dumps(dict(id=t['id'], kind=t['kind'], status=t['status'], shares=t.get('shares'),
                                                   candidates=ranked_candidates(A, t, A.dvd.T_NM / 1000)),
                                              separators=(',', ':'), allow_nan=False) + chr(10))
                    rule = control['targets'].get(t['id'], {})
                    if rule.get('reference_stale'):
                        t.update(reference_stale=True, latest_reference_target_purity=rule['target_purity'], status='searched')
                        stale += 1
                    light[t['id']] = dict(id=t['id'], kind=t['kind'], ring=t.get('ring'), status=t['status'],
                                          campaign_pass=t.get('campaign_pass', 0), budget_round=t.get('budget_round', 0),
                                          retired=bool(t.get('retired')), runs=light_runs(t.get('runs', [])),
                                          whole=sum(c.get('measurement') == 'whole' for c in t.get('refined_top', [])),
                                          gpu_done=sum(bool(r.get('complete')) for r in t.get('runs', [])) >= plan['restarts'],
                                          refined=A.campaign.round_refined(t, plan['restarts']))
                    for k in HEAVY:
                        t.pop(k, None)
                    f.write(json.dumps(t, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n')
            parts.append(part)
            del merged; gc.collect()
            log(f'group {g + 1}/{len(groups)} merged, {available_mb()} MB free')
    finally:
        A.merge.Journal = real_journal
        cand.close()
    os.replace(work / 'candidates.jsonl.tmp', work / 'candidates.jsonl')

    # One compacted journal in global order, chained exactly like Journal.compact.
    snapshot = work / 'snapshot.jsonl'
    where = {}
    for part in parts:
        offset = 0
        with open(part, 'rb') as f:
            for raw in f:
                where[json.loads(raw)['id']] = (part, offset); offset += len(raw)
    previous = '0' * 64
    with open(snapshot, 'w', encoding='utf-8', newline='\n') as out:
        handles = {p: open(p, 'rb') for p in parts}
        try:
            for i, tid in enumerate(sorted(where, key=order.__getitem__)):
                part, offset = where[tid]
                handles[part].seek(offset)
                t = json.loads(handles[part].readline())
                event = dict(sequence=i, previous_hash=previous, timestamp=time.time(), reason='compacted target snapshot',
                             id=t['id'], media=t['media'], kind=t['kind'], periods=t['periods'], shares=t['shares'],
                             grid_bin=t.get('grid_bin'), status=t['status'], independent_runs=t.get('independent_runs'),
                             best_purity_per_run=t.get('best_purity_per_run'), target=t,
                             compacted_from=dict(path='disc-neo build snapshot', inputs=[p.name for p in journals]))
                previous = A.digest(event)
                out.write(A.journal.canonical(dict(event, event_hash=previous)) + '\n')
        finally:
            for h in handles.values():
                h.close()
    for part in parts:
        part.unlink()
    mb = snapshot.stat().st_size / 2**20
    log(f'snapshot {mb:.0f} MB; running atlas merge()')
    if mb > args.max_snapshot_mb:
        raise SystemExit(f'snapshot {mb:.0f} MB exceeds --max-snapshot-mb {args.max_snapshot_mb}; not loading it')
    guard.check('atlas merge')
    destination = work / 'atlas_dvd.json'
    out = A.merge.merge([snapshot], A.dvd, ev / 'imports', destination)

    targets = list(light.values())
    progress = A.campaign.ring_progress(plan, targets, control)
    stats = progress_stats(plan, light)
    (work / 'target-progress.json').write_text(json.dumps(
        {t['id']: {k: t[k] for k in ('status', 'gpu_done', 'refined', 'whole')} for t in targets}), encoding='utf-8')
    machines = {}
    for path in journals:
        info = indexes[str(path)]
        ids = info['latest'].keys()
        machines[roles[path.name]] = dict(events=info['events'], targets=len(ids), tail_hash=info['tail'],
            targets_with_whole_block_result=sum(1 for tid in ids if light.get(tid, {}).get('whole')))
    helper_ids = set().union(*[indexes[str(p)]['latest'].keys() for p in journals if roles[p.name].startswith('cpu-helper:')])
    gpu_ids = set().union(*[indexes[str(p)]['latest'].keys() for p in journals if roles[p.name].startswith(('gpu:', 'gpu-extra:'))])
    helper = dict(journals=sum(roles[p.name].startswith('cpu-helper:') for p in journals), targets=len(helper_ids),
                  all_restarts_complete=sum(1 for tid in helper_ids if light.get(tid, {}).get('gpu_done')),
                  also_in_gpu_journals=len(helper_ids & gpu_ids),
                  refined=sum(1 for tid in helper_ids if light.get(tid, {}).get('refined')))
    log('CPU helpers', helper)
    meta = dict(queue=queue_info, reference_stale_marked=stale, machines=machines, cpu_helper=helper, progress=stats,
                ring_progress=progress, snapshot_sha256=sha256(snapshot), snapshot_bytes=snapshot.stat().st_size)
    (work / 'export-meta.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    snapshot.unlink()
    return out, meta


def progress_stats(plan, light):
    restarts = plan['restarts']
    jobs = [j for b in plan['shards'].values() for j in b['jobs']]
    def summary(rows):
        n = len(rows)
        gpu = sum(1 for j in rows if light.get(j['id'], {}).get('gpu_done'))
        cpu = sum(1 for j in rows if light.get(j['id'], {}).get('refined'))
        anyw = sum(1 for j in rows if light.get(j['id'], {}).get('whole'))
        conv = sum(1 for j in rows if light.get(j['id'], {}).get('status') in ('converged', 'exhausted'))
        return dict(jobs=n, gpu_restarts_complete=gpu, cpu_refined_round=cpu, with_whole_block_result=anyw,
                    converged_or_exhausted=conv,
                    gpu_fraction=round(gpu / n, 4) if n else None, refined_fraction=round(cpu / n, 4) if n else None)
    coarse = [j for j in jobs if not j.get('campaign_pass', 0)]
    dense = [j for j in jobs if j.get('campaign_pass', 0)]
    statuses = {}
    for t in light.values():
        if not t['retired']:
            statuses[t['status']] = statuses.get(t['status'], 0) + 1
    by_kind = {}
    for j in coarse:
        by_kind.setdefault(j['kind'], []).append(j)
    return dict(restarts_required=restarts, coarse_pass=summary(coarse), dense_pass=summary(dense), all_jobs=summary(jobs),
                coarse_by_kind={k: summary(v) for k, v in sorted(by_kind.items())}, status_counts=statuses)


# --------------------------------------------------------------------------- tables

def fmt(x, digits=6):
    if x is None:
        return ''
    if isinstance(x, float):
        return f'{x:.{digits}g}'
    return str(x)


def joined(xs, digits=6):
    return ';'.join(fmt(float(x), digits) for x in xs) if xs else ''


def write_csv(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def build_candidate_tables(source, folder, winners):
    """candidates.json (per target, ranked) and candidates.csv (one row per target x candidate)."""
    header = ['target_id', 'kind', 'target_status', 'rank', 'basis', 'is_current_winner', 'spec', 'k', 'main_period_um',
              'periods_um', 'purity', 'objective', 'purity_basis', 'F512_percent', 'risk', 'risk_basis', 'leakage_max',
              'proxy_score', 'sources']
    stats = dict(targets=0, targets_with_candidates=0, rows=0, whole=0, proxy=0, rank1_is_winner=0, winners=0,
                 rank1_not_winner=[])
    counts = {}
    fc = open(folder / 'candidates.csv', 'w', encoding='utf-8', newline='')
    fj = open(folder / 'candidates.json', 'w', encoding='utf-8', newline=chr(10))
    with open(source, encoding='utf-8') as src, fc, fj:
        w = csv.writer(fc, lineterminator=chr(10)); w.writerow(header)
        fj.write('{"schema":"disc-neo candidates v1","ranking":"whole-block first by atlas rank(), then gpu-proxy","targets":{')
        first = True
        for line in src:
            t = json.loads(line)
            stats['targets'] += 1
            cands = t['candidates']
            win = winners.get(t['id'])
            for c in cands:
                c['is_current_winner'] = (bool(win) and c['spec'] == win['spec'].upper() and c['basis'] == 'whole-block'
                    and [round(x, 9) for x in c['periods_T']] == [round(x, 9) for x in win['periods_T']])
            if win:
                stats['winners'] += 1
                if cands and cands[0]['is_current_winner']:
                    stats['rank1_is_winner'] += 1
                else:
                    stats['rank1_not_winner'].append(t['id'])
            counts[t['id']] = (len(cands), sum(c['basis'] == 'whole-block' for c in cands))
            if cands:
                stats['targets_with_candidates'] += 1
            for c in cands:
                stats['rows'] += 1
                stats['whole' if c['basis'] == 'whole-block' else 'proxy'] += 1
                w.writerow([t['id'], t['kind'], t['status'], c['rank'], c['basis'], int(c['is_current_winner']), c['spec'],
                            c['k'], fmt(c['main_period_um']), joined(c['periods_um']), joined(c['purity'] or [], 4),
                            fmt(c['objective'], 4), c['purity_basis'], fmt(c['F512_percent'], 4), c['risk'], c['risk_basis'],
                            fmt(c['leakage_max'], 4), fmt(c['proxy_score'], 4), ';'.join(c['sources'])])
            fj.write(('' if first else ',') + json.dumps(t['id']) + ':' +
                     json.dumps(dict(kind=t['kind'], status=t['status'], shares=t['shares'], candidates=cands),
                                separators=(',', ':'), allow_nan=False))
            first = False
        fj.write('}}' + chr(10))
    stats['rank1_not_winner_count'] = len(stats['rank1_not_winner'])
    stats['rank1_not_winner'] = stats['rank1_not_winner'][:20]
    return stats, counts


def build_tables(atlas, target_meta, folder, T_um, cand_counts=None):
    cand_counts = cand_counts or {}
    targets = {t['id']: t for t in atlas['targets']}
    winners = {r['id']: r for r in atlas['atlas_target_winners'] + atlas['ladder'] + atlas['dark']}
    def tmeta(tid, key):
        return (targets.get(tid) or {}).get(key)
    singles = [r for r in atlas['atlas_target_winners'] if r.get('kind') == 'single']
    singles.sort(key=lambda r: r['periods_um'][0])
    rows = []
    for r in singles:
        d = r.get('delta') or {}
        rows.append([r['id'], r.get('rev', 0), r['spec'], r['k'], fmt(r['periods_um'][0]), fmt(r['purity'][0], 4),
                     r.get('purity_basis'), r.get('measurement'), fmt(r.get('F512_percent'), 4), r.get('risk'),
                     r.get('status'), r.get('verified'), tmeta(r['id'], 'ring'), tmeta(r['id'], 'density_tier'),
                     fmt(tmeta(r['id'], 'pose_visible_fraction'), 3),
                     *(fmt(v, 4) for name in ('blue', 'green', 'red') for v in d.get(name, ('', ''))),
                     fmt(d.get('red_edge_700nm'), 4), *cand_counts.get(r['id'], ('', ''))])
    n_single = write_csv(folder / 'singles.csv',
        ['id', 'rev', 'spec', 'k', 'period_um', 'purity', 'purity_basis', 'measurement', 'F512_percent', 'risk',
         'status', 'verified', 'ring', 'density_tier', 'visible_fraction_design_poses',
         'delta_blue_lo', 'delta_blue_hi', 'delta_green_lo', 'delta_green_hi', 'delta_red_lo', 'delta_red_hi',
         'delta_red_edge_700nm', 'candidates_total', 'candidates_whole_block'], rows)
    multi = [r for r in atlas['atlas_target_winners'] if r.get('kind') in ('two_line', 'three_line')]
    multi.sort(key=lambda r: (r['kind'], r['periods_um']))
    rows = []
    for r in multi:
        shares = r.get('target_shares') or r.get('weights') or []
        pur = r.get('purity') or []
        weighted = min((p / w for p, w in zip(pur, shares) if w > 0), default=None)
        rows.append([r['id'], r.get('rev', 0), r['kind'], r['spec'], r['k'], joined(r['periods_um']), joined(shares, 4),
                     joined(pur, 4), fmt(weighted, 4), r.get('purity_basis'), r.get('measurement'),
                     fmt(r.get('F512_percent'), 4), r.get('risk'), r.get('status'), r.get('verified'),
                     tmeta(r['id'], 'ring'), tmeta(r['id'], 'density_tier'), *cand_counts.get(r['id'], ('', ''))])
    n_multi = write_csv(folder / 'multi_line.csv',
        ['id', 'rev', 'kind', 'spec', 'k', 'periods_um', 'shares', 'purity', 'min_purity_over_share', 'purity_basis',
         'measurement', 'F512_percent', 'risk', 'status', 'verified', 'ring', 'density_tier',
         'candidates_total', 'candidates_whole_block'], rows)
    from fractions import Fraction
    rows = []
    for t in atlas['targets']:
        if t.get('retired'):
            continue
        lo = hi = None
        if t.get('grid_bin') is not None and t.get('grid_step'):
            anchor = float(Fraction(str(t.get('grid_anchor') or '6')))
            domains = t.get('density_period_domains') or [dict(anchor=t.get('grid_anchor') or '6', bin=t['grid_bin'], step=t['grid_step'])]
            edges = [(float(Fraction(str(d['anchor']))) * (1 + d['step']) ** d['bin'],
                      float(Fraction(str(d['anchor']))) * (1 + d['step']) ** (d['bin'] + 1)) for d in domains]
            lo, hi = min(e[0] for e in edges) * T_um, max(e[1] for e in edges) * T_um
        w = winners.get(t['id'])
        pur = (w or {}).get('purity') or []
        meta = target_meta.get(t['id'], {})
        rows.append([t['id'], t['kind'], fmt(lo), fmt(hi), fmt(t.get('grid_step')), t.get('density_tier'),
                     t.get('campaign_pass'), t.get('ring'), fmt(t.get('usefulness'), 3),
                     fmt(t.get('pose_visible_fraction'), 3), t.get('status'),
                     int(t.get('status') in ('converged', 'exhausted')), int(bool(meta.get('refined'))),
                     joined(pur, 4), fmt(max(pur), 4) if pur else '', (w or {}).get('measurement', ''),
                     t.get('rev'), t.get('verified')])
    rows.sort(key=lambda r: (r[1], float(r[2]) if r[2] else 0.))
    n_cov = write_csv(folder / 'coverage.csv',
        ['id', 'kind', 'period_lo_um', 'period_hi_um', 'grid_step', 'density_tier', 'campaign_pass', 'ring',
         'usefulness', 'visible_fraction_design_poses', 'status', 'converged', 'cpu_refined_round',
         'best_purity', 'best_purity_max', 'measurement', 'rev', 'verified'], rows)
    return dict(singles=n_single, multi_line=n_multi, coverage=n_cov,
                two_line=sum(r['kind'] == 'two_line' for r in multi), three_line=sum(r['kind'] == 'three_line' for r in multi))


# --------------------------------------------------------------------------- docs and cards

def texture_cards(dest, ref):
    names = subprocess.check_output(['git', '-C', str(REPO), 'ls-tree', '-r', '--name-only', ref, '--', 'docs/texture-cards'],
                                    text=True).split()
    names = [n for n in names if allowed(n)]
    if not names:
        raise SystemExit(f'docs/texture-cards not found at {ref}')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', ref], text=True).strip()
    data = subprocess.check_output(['git', '-C', str(REPO), 'archive', '--format=tar', commit, '--', *names])
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            rel = Path(m.name).relative_to('docs/texture-cards')
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tar.extractfile(m).read())
    last = subprocess.check_output(['git', '-C', str(REPO), 'log', '-1', '--format=%H', commit, '--', 'docs/texture-cards'],
                                   text=True).strip()
    return dict(ref=ref, commit=commit, last_change_commit=last, path='docs/texture-cards', files=len(names))


def render(template, values):
    text = drop_missing_doc_lines((TEMPLATES / template).read_text(encoding='utf-8'), '{{%s}}')
    for k, v in values.items():
        text = text.replace('{{' + k + '}}', str(v))
    if '{{' in text:
        start = text.index('{{')
        raise SystemExit(f'unfilled placeholder in {template}: {text[start:start + 40]}')
    return text


# Links follow the release, not main: the tag must be exactly the one published (release notes use v[VERSION]).
DP_DOC_BASE = f'https://github.com/Ashley-QwQ/disc-probe/blob/v{VERSION}/'
DP_DOCS = {
    'COLOUR_EN': ('docs/colour.md', 'In the web app'),
    'COLOUR_ZH': ('docs/colour.zh.md', '在网页里做'),
    'THEORY_EN': ('docs/how-discs-make-pictures.md', ''),
    'THEORY_ZH': ('docs/how-discs-make-pictures.zh.md', ''),
    'SHOWCASE_PHOTO': ('docs/showcase/showd_8145_card.jpg', ''),
}


# Shown only when both files are in the source being released; otherwise the line is left out, never a dead link.
OPTIONAL_DOCS = ('THEORY_EN', 'THEORY_ZH')


def available_docs():
    present = {key for key, (path, _) in DP_DOCS.items() if (REPO / path).is_file()}
    if not all(key in present for key in OPTIONAL_DOCS):
        present -= set(OPTIONAL_DOCS)
    return {key: DP_DOCS[key] for key in DP_DOCS if key in present}


def drop_missing_doc_lines(text, pattern):
    missing = [key for key in OPTIONAL_DOCS if key not in available_docs()]
    return ''.join(line for line in text.splitlines(keepends=True)
                   if not any(pattern % key in line for key in missing))


def doc_url(path, heading):
    return DP_DOC_BASE + path + ('#' + heading.lower().replace(' ', '-') if heading else '')


def require_onboarding_docs():
    problems = []
    for key, (path, heading) in DP_DOCS.items():
        if key in OPTIONAL_DOCS:
            continue
        source = REPO / path
        if not source.is_file():
            problems.append(f'missing {path}')
        elif heading and f'## {heading}' not in source.read_text(encoding='utf-8-sig').splitlines():
            problems.append(f'missing section "{heading}" in {path}')
    if not all(key in available_docs() for key in OPTIONAL_DOCS):
        log('NOTE: docs/how-discs-make-pictures(.zh).md are not both present; the "how it works" link is left out')
    if problems:
        raise SystemExit('Disc Neo onboarding links require the Disc Probe documents:\n' + '\n'.join(problems))


def canonical_spec(spec):
    """The texlib byte-pattern identity, without rotation or reversal."""
    spec = spec.upper()
    for width in range(2, len(spec), 2):
        if len(spec) % width == 0 and spec == spec[:width] * (len(spec) // width):
            return spec[:width]
    return spec


def write_colour_evidence(cands, stage):
    """Join the reader's candidates to exact byte specs found in physical records."""
    specs = {canonical_spec(c[3]) for c in cands}
    with (TEMPLATES / 'colour-evidence.csv').open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        matches = [row for row in reader if row['spec'] in specs]
    with (stage / 'colour-evidence.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=reader.fieldnames, lineterminator='\n')
        writer.writeheader()
        writer.writerows(matches)
    shutil.copyfile(TEMPLATES / 'colour-card-photo.jpg', stage / 'colour-card-photo.jpg')
    shutil.copyfile(TEMPLATES / 'character-disc-photo.png', stage / 'character-disc-photo.png')
    return dict(CARD_SPECS=sum(row['colour_card_sample'] == '1' for row in matches),
                SHOW_SPECS=sum(row['showcase_a_to_e'] == '1' for row in matches),
                MODEL_SPECS=len(specs) - len(matches))


def pct(a, b):
    return f'{100 * a / b:.1f}' if b else '0'


def helper_notes(helper):
    """The status-table sentence about CPU helpers; empty when none finished a target."""
    n = (helper or {}).get('all_restarts_complete', 0)
    if not n:
        return dict(HELPER_NOTE_ZH='', HELPER_NOTE_EN='')
    return dict(HELPER_NOTE_ZH=f'跑完重启的目标里有 {n} 个是 11-14 起加开的 CPU 帮手跑的（同一套搜索代码，跑在 CPU 上），'
                               f'它们本轮不安排精修，停在粗搜。',
                HELPER_NOTE_EN=f' {n} of them were run by CPU helpers added on 11-14 (the same search code on CPUs);'
                               f' those targets get no refinement this run and stay at the coarse stage.')


def doc_values(meta, counts, prov):
    p = meta['progress']; c = p['coarse_pass']; d = p['dense_pass']; a = p['all_jobs']
    s = p['status_counts']
    return dict(**helper_notes(meta.get('cpu_helper')),
        VERSION=VERSION, EPOCH=prov['epoch'], SNAPSHOT_UTC=prov['snapshot_utc'], SNAPSHOT_DATE=prov['snapshot_utc'][:10],
        TARGETS=sum(s.values()), CONVERGED=s.get('converged', 0) + s.get('exhausted', 0), SEARCHED=s.get('searched', 0),
        TODO=s.get('todo', 0),
        COARSE_JOBS=c['jobs'], COARSE_GPU=c['gpu_restarts_complete'], COARSE_GPU_PCT=pct(c['gpu_restarts_complete'], c['jobs']),
        COARSE_REF=c['cpu_refined_round'], COARSE_REF_PCT=pct(c['cpu_refined_round'], c['jobs']),
        DENSE_JOBS=d['jobs'], DENSE_GPU=d['gpu_restarts_complete'], DENSE_GPU_PCT=pct(d['gpu_restarts_complete'], d['jobs']),
        DENSE_REF=d['cpu_refined_round'], DENSE_REF_PCT=pct(d['cpu_refined_round'], d['jobs']),
        ALL_JOBS=a['jobs'], ALL_GPU_PCT=pct(a['gpu_restarts_complete'], a['jobs']), ALL_REF_PCT=pct(a['cpu_refined_round'], a['jobs']),
        WHOLE_TARGETS=a['with_whole_block_result'], WHOLE_PCT=pct(a['with_whole_block_result'], a['jobs']),
        SINGLES=counts['singles'], TWO_LINE=counts['two_line'], THREE_LINE=counts['three_line'],
        COVERAGE_ROWS=counts['coverage'], CAND_ROWS=counts['candidates']['rows'], CAND_WHOLE=counts['candidates']['whole'],
        CAND_PROXY=counts['candidates']['proxy'], CAND_TARGETS=counts['candidates']['targets_with_candidates'], LADDER=counts['ladder'], DARK=counts['dark'],
        ORDER2=counts['order2'], ORDER3=counts['order3'], OBSERVATIONS=counts['observations'],
        IMPORTED=counts['imported_observations'], END_DATE=prov['campaign']['planned_end_utc'][:10], HARD_DATE=prov['campaign']['deadline_utc'][:10],
        SNAPSHOT_HUMAN=prov['snapshot_utc'][:16].replace('T', ' ') + ' UTC',
        CARDS_COMMIT=prov['texture_cards']['commit'][:7])


def write_license(dest):
    gpl = (REPO / 'LICENSE').read_text(encoding='utf-8')
    head = render('LICENSE.head', {})
    (dest / 'LICENSE').write_text(head + '\n' + gpl, encoding='utf-8', newline='\n')


# --------------------------------------------------------------------------- offline reader

READER_KINDS = ('single', 'two_line', 'three_line', 'ladder', 'dark', 'order2', 'order3')
READER_STATUS = ('todo', 'searched', 'converged', 'exhausted')
READER_RISK = ('low (A5-like)', 'low F512, frames lean', 'as 92', 'HIGH', 'UNKNOWN')
FONT = Path('discprobe/web/fonts/Archivo-VF-latin.woff2')
ART = {'PAPER_PAPER': 'discprobe/web/home/newplan/paper_paper.webp', 'PAPER_DARK': 'discprobe/web/home/newplan/paper_dark.webp',
       'SHADOW_PAPER': 'discprobe/web/home/newplan/paper_shadow_paper.webp', 'SHADOW_DARK': 'discprobe/web/home/newplan/paper_shadow_dark.webp',
       'DESK_PAPER': 'discprobe/web/home/caltop/anim/desk_paper.webp', 'DESK_DARK': 'discprobe/web/home/caltop/anim/desk_dark.webp'}


def period_interval(t, T_um):
    from fractions import Fraction
    if t.get('grid_bin') is None or not t.get('grid_step'):
        return None, None
    domains = t.get('density_period_domains') or [dict(anchor=t.get('grid_anchor') or '6', bin=t['grid_bin'], step=t['grid_step'])]
    edges = [(float(Fraction(str(d['anchor']))) * (1 + d['step']) ** d['bin'],
              float(Fraction(str(d['anchor']))) * (1 + d['step']) ** (d['bin'] + 1)) for d in domains]
    return min(e[0] for e in edges) * T_um, max(e[1] for e in edges) * T_um


def find_art(ref):
    """The web UI's desk grain and paper sheet (newplan page), from the ref or a checkout on disk."""
    import base64
    out = {}
    for key, rel in ART.items():
        data = None
        try:
            data = subprocess.check_output(['git', '-C', str(REPO), 'show', f'{ref}:{rel}'], stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            for root in (REPO, REPO.parent / 'release-packs', Path('D:/disc-probe')):
                if (root / rel).is_file():
                    data = (root / rel).read_bytes(); break
        if data is None:
            raise SystemExit(f'reader art not found: {rel}')
        out[key] = 'data:image/webp;base64,' + base64.b64encode(data).decode('ascii')
    return out


def find_font(ref):
    """Archivo (SIL OFL 1.1) as the web UI ships it: git ref first, then checkouts on disk."""
    lic = FONT.with_name('OFL-Archivo.txt')
    try:
        return (subprocess.check_output(['git', '-C', str(REPO), 'show', f'{ref}:{FONT.as_posix()}'], stderr=subprocess.DEVNULL),
                subprocess.check_output(['git', '-C', str(REPO), 'show', f'{ref}:{lic.as_posix()}'], stderr=subprocess.DEVNULL).decode('utf-8'))
    except subprocess.CalledProcessError:
        pass
    for root in (REPO, REPO.parent / 'release-packs', Path('D:/disc-probe')):
        if (root / FONT).is_file() and (root / lic).is_file():
            return (root / FONT).read_bytes(), (root / lic).read_text(encoding='utf-8')
    log('Archivo font not found; the reader falls back to system fonts')
    return None, None


def reader_brand_assets():
    import base64
    web = REPO / 'discprobe' / 'web'
    assets = {'TOKENS': (web / 'tokens.css').read_text(encoding='utf-8')}
    for key, name, mime in (
        ('WORDMARK_PAPER', 'disc-neo-wordmark-paper.svg', 'image/svg+xml'),
        ('WORDMARK_INK', 'disc-neo-wordmark-ink.svg', 'image/svg+xml'),
        ('FAVICON', 'neo/favicon.ico', 'image/x-icon'),
    ):
        data = base64.b64encode((web / 'brand' / name).read_bytes()).decode('ascii')
        assets[key] = f'data:{mime};base64,{data}'
    return assets


def build_reader(coverage_csv, cand_path, values, dest, cards_ref):
    """index.html: one offline page with the data gzip+base64 inside (file:// cannot fetch siblings).

    Targets come from coverage.csv (every active target with its period range and search state), so the
    page can be rebuilt without loading the full export."""
    import base64, gzip
    r4 = lambda x: None if x in (None, '') else round(float(x), 4)
    targets, index = [], {}
    with open(coverage_csv, encoding='utf-8', newline='') as f:
        for t in csv.DictReader(f):
            index[t['id']] = len(targets)
            targets.append([t['id'], READER_KINDS.index(t['kind']) if t['kind'] in READER_KINDS else 0,
                            r4(t['period_lo_um']), r4(t['period_hi_um']),
                            READER_STATUS.index(t['status']) if t['status'] in READER_STATUS else 0,
                            1 if t['density_tier'] == 'dense' else 0, int(t['ring']) if t['ring'] not in ('', 'None') else None,
                            r4(t['visible_fraction_design_poses']), None, 0, 0, int(t['cpu_refined_round'] == '1'), None])
    cands = []
    with open(cand_path, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            i = index.get(row['id'])
            if i is None:
                continue
            best = None
            for c in row['candidates']:
                whole = c['basis'] == 'whole-block'
                pur = [r4(x) for x in (c.get('purity') or [])]
                if whole and pur and best is None:
                    best = max(pur)
                risk = READER_RISK.index(c['risk']) if c['risk'] in READER_RISK else 4
                cands.append([i, c['rank'], 1 if whole else 0, c['spec'], r4(c.get('main_period_um')),
                              [r4(x) for x in c.get('periods_um') or []], pur, risk, r4(c.get('F512_percent'))])
            targets[i][8] = best
            targets[i][12] = [r4(x) for x in row.get('shares') or []] or None
            targets[i][9] = sum(c['basis'] == 'whole-block' for c in row['candidates'])
            targets[i][10] = len(row['candidates'])
    meta = dict(version=values['VERSION'], snapshot=values['SNAPSHOT_HUMAN'], epoch=values['EPOCH'],
                end=values['END_DATE'], hard=values['HARD_DATE'], coarse_gpu=values['COARSE_GPU_PCT'],
                coarse_ref=values['COARSE_REF_PCT'], whole_pct=values['WHOLE_PCT'], targets=values['TARGETS'],
                converged=values['CONVERGED'], kinds=READER_KINDS, status=READER_STATUS, risk=READER_RISK,
                progress={k: values['_progress'][k] for k in ('coarse_pass', 'dense_pass', 'all_jobs')})
    blob = json.dumps(dict(meta=meta, t=targets, c=cands), separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    packed = base64.b64encode(gzip.compress(blob.encode('utf-8'), 9)).decode('ascii')
    font, ofl = find_font(cards_ref)
    html = drop_missing_doc_lines((TEMPLATES / 'reader.html').read_text(encoding='utf-8'), '__NEO_%s__')
    evidence = {key: f'{count:,}' for key, count in write_colour_evidence(cands, dest.parent).items()}
    links = {key: doc_url(*target) for key, target in available_docs().items()}
    values.update(links, **evidence)
    for key, val in {**find_art(cards_ref), **reader_brand_assets(), **links, **evidence}.items():
        assert html.count(f'__NEO_{key}__') >= 1, key
        html = html.replace(f'__NEO_{key}__', val)
    for key, val in (('__NEO_DATA__', packed), ('__NEO_FONT__', base64.b64encode(font).decode('ascii') if font else ''),
                     ('__NEO_FONT_LICENSE__', ofl.replace('--', '- -') if ofl else 'Archivo not embedded; system fonts used.'),
                     ('__NEO_VERSION__', values['VERSION']), ('__NEO_SNAPSHOT__', values['SNAPSHOT_HUMAN'])):
        assert html.count(key) >= 1, key
        html = html.replace(key, val)
    dest.write_text(html, encoding='utf-8', newline=chr(10))
    return dict(targets=len(targets), candidates=len(cands), json_bytes=len(blob), html_bytes=dest.stat().st_size)


def write_docs(folder, cand_path, values, stage, reader_ref):
    values = dict(values)
    reader = build_reader(folder / 'coverage.csv', cand_path, values, stage / 'index.html', reader_ref)
    for name in ('README.md', 'README.zh.md', 'SCHEMA.md'):
        (stage / name).write_text(render(name, values), encoding='utf-8', newline='\n')
    return reader


# --------------------------------------------------------------------------- checks

def check(root):
    """Same rules as tools/release.py validate_neo/package_files, plus content sanity."""
    problems = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [n for n in dirs if allowed(Path(base) / n)]
        for name in dirs + names:
            path = Path(base) / name
            if not allowed(path) or path.is_symlink():
                problems.append(f'excluded or linked path: {path}')
            elif name in names and not path.is_file():
                problems.append(f'not a regular file: {path}')
    for name in NEO_REQUIRED:
        if not (root / name).is_file():
            problems.append('missing ' + name)
    for rel in ('atlas/dvd/atlas_dvd.json', 'atlas/dvd/singles.csv', 'atlas/dvd/multi_line.csv',
                'atlas/dvd/candidates.csv', 'atlas/dvd/candidates.json', 'index.html',
                'atlas/dvd/coverage.csv', 'texture-cards/texture_cards_v3_led.pdf', 'texture-cards/texture_cards_v3_d65.pdf'):
        if not (root / rel).is_file() or not (root / rel).stat().st_size:
            problems.append('missing or empty ' + rel)
    if (root / 'PROVENANCE.json').is_file():
        prov = json.loads((root / 'PROVENANCE.json').read_text(encoding='utf-8'))
        for rel, row in prov.get('package_files', {}).items():
            if rel in ('PROVENANCE.json',):
                continue
            if not (root / rel).is_file() or sha256(root / rel) != row['sha256']:
                problems.append('hash mismatch ' + rel)
    lic = (root / 'LICENSE').read_text(encoding='utf-8') if (root / 'LICENSE').is_file() else ''
    if 'GPL-3.0-or-later' not in lic or 'GNU GENERAL PUBLIC LICENSE' not in lic:
        problems.append('LICENSE lacks the GPL-3.0-or-later notice or text')
    if (root / 'index.html').is_file():
        try:
            import base64, gzip, re
            html = (root / 'index.html').read_text(encoding='utf-8')
            doc_urls = {doc_url(*target) for target in DP_DOCS.values()}
            external = re.findall(r'\b(src|href)\s*=\s*[\"\'](https?://[^\"\']+)[\"\']', html)
            if '__NEO_' in html or any(attr == 'src' or url not in doc_urls for attr, url in external):
                problems.append('reader has unresolved placeholders or unexpected external URLs')
            packed = re.search(r'const DATA_B64 = "([A-Za-z0-9+/=]+)";', html)
            data = json.loads(gzip.decompress(base64.b64decode(packed.group(1), validate=True)))
            if len(data['t']) != data['meta']['targets'] or len({t[0] for t in data['t']}) != len(data['t']):
                problems.append('reader target counts or IDs disagree')
            if any(not 0 <= c[0] < len(data['t']) for c in data['c']):
                problems.append('reader candidate references missing target')
            if (root / 'PROVENANCE.json').is_file():
                if len(data['c']) != prov['counts']['candidates']['rows']:
                    problems.append('reader candidate count disagrees with provenance')
        except (ValueError, AttributeError, KeyError, OSError) as exc:
            problems.append('reader data check failed: ' + str(exc))
    return problems


def inventory(root):
    rows = {}
    paths = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [n for n in dirs if allowed(Path(base) / n)]
        paths.extend(Path(base) / n for n in names if allowed(Path(base) / n))
    for path in sorted(paths):
        rel = path.relative_to(root).as_posix()
        rows[rel] = dict(bytes=path.stat().st_size, sha256=sha256(path))
    return rows


def docs_only(args):
    """Rebuild the words and the reader on top of the staged data (no atlas load, a few hundred MB of RAM)."""
    report = json.loads((args.work / 'build-report.json').read_text(encoding='utf-8'))
    prov = json.loads((args.out / 'PROVENANCE.json').read_text(encoding='utf-8'))
    values = dict(report['values']); values['_progress'] = prov['progress']
    for k, v in helper_notes(prov.get('cpu_helper')).items():
        values.setdefault(k, v)
    stage = args.out.with_name(args.out.name + '.building')
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(args.out, stage)
    prov['reader'] = write_docs(stage / 'atlas' / 'dvd', args.work / 'candidates.jsonl', values, stage, args.reader_ref)
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain', '--', 'tools/build_neo.py',
                                          'tools/neo_templates'], text=True).strip())
    prov['builder'] = dict(script='tools/build_neo.py', commit=head, uncommitted_changes=dirty, python=platform.python_version(),
                           docs_only_rebuild_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
    (stage / 'PROVENANCE.json').unlink()
    prov['package_files'] = inventory(stage)
    (stage / 'PROVENANCE.json').write_text(json.dumps(prov, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    problems = check(stage)
    if problems:
        raise SystemExit('staging check failed:\n' + '\n'.join(problems))
    old = args.out.with_name(args.out.name + '.previous')
    if old.exists():
        shutil.rmtree(old)
    os.replace(args.out, old)
    os.replace(stage, args.out)
    shutil.rmtree(old)
    log('PASS (docs only)', args.out, prov['reader'])
    return 0


# --------------------------------------------------------------------------- main

class JSONStream:
    """Incremental stdlib JSON decoder; memory is bounded by the largest item."""
    def __init__(self, stream):
        self.stream, self.buf, self.pos, self.eof = stream, '', 0, False
        self.decoder = json.JSONDecoder()

    def more(self):
        chunk = self.stream.read(1 << 20)
        self.buf = self.buf[self.pos:] + chunk
        self.pos = 0
        self.eof = not chunk

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if self.eof:
                return ''
            self.more()

    def take(self, expected):
        if self.peek() != expected:
            raise ValueError(f'expected JSON delimiter {expected!r}')
        self.pos += 1

    def value(self):
        self.peek()
        while True:
            try:
                result, end = self.decoder.raw_decode(self.buf, self.pos)
                # A number at a chunk boundary may continue in the next chunk.
                if end == len(self.buf) and not self.eof:
                    self.more(); continue
                self.pos = end
                return result
            except json.JSONDecodeError:
                if self.eof:
                    raise
                old = len(self.buf) - self.pos
                self.more()
                if len(self.buf) == old:
                    self.eof = True


def export_fields(path):
    """Yield scalar fields and individual array entries, including empty arrays."""
    with open(path, encoding='utf-8') as f:
        s = JSONStream(f)
        s.take('{')
        while s.peek() != '}':
            key = s.value(); s.take(':')
            if s.peek() == '[':
                s.take('[')
                yield key, None, 'array'
                while s.peek() != ']':
                    yield key, s.value(), 'item'
                    if s.peek() != ']':
                        s.take(',')
                s.take(']')
            else:
                yield key, s.value(), 'scalar'
            if s.peek() != '}':
                s.take(',')
        s.take('}')
        if s.peek():
            raise ValueError('trailing data after export')


def export_index(path, guard):
    """Keep only table fields, never the large observations/metrics arrays."""
    keep = {'targets', 'atlas_target_winners', 'ladder', 'dark', 'order2', 'order3'}
    atlas, counts = {}, {}
    for key, value, kind in export_fields(path):
        if kind == 'array':
            counts[key] = 0
            if key in keep:
                atlas[key] = []
        elif kind == 'item':
            counts[key] += 1
            if key in keep:
                atlas[key].append({k: v for k, v in value.items() if k != 'metrics'})
            if counts[key] % 500 == 0:
                guard.check('reading official export ' + key)
        elif key == 'T_um':
            atlas[key] = value
    return atlas, counts


def verify_snapshot(root, epoch):
    """Verify every manifest entry before importing atlas code or building output."""
    rows = []
    for line in (root / 'SHA256SUMS').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        name = name.lstrip('*')
        path = root / name
        if not allowed(path) or Path(name).name != name:
            raise ValueError('unsafe snapshot manifest path')
        actual = sha256(path)
        if actual != expected:
            raise ValueError('snapshot SHA256 mismatch: ' + name)
        rows.append(dict(role=name, source=str(path), present=True, bytes=path.stat().st_size, sha256=actual,
                         source_mtime_utc=dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(timespec='seconds')))
        log('verified', name)
    required = {'atlas_dvd.json', 'plan.json', 'daily-status.json', f'campaign-{epoch}.json', f'control-{epoch}.json'}
    names = {Path(r['source']).name for r in rows}
    daily = [root / n for n in names if n.startswith(f'daily-{epoch}-') and n.endswith('.jsonl')]
    if not required <= names or len(daily) != 1:
        raise ValueError('snapshot manifest lacks required inputs or exactly one daily')
    return rows, daily[0]


def verify_atlas_code(root):
    """Pin imported code and legacy imports to the card's commit, without a live checkout import."""
    raw = subprocess.check_output(['git', '-C', 'D:/dp-dev/integ', 'archive', '594c677', 'evidence/atlas'])
    checked = 0
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar:
            if not member.isfile() or not allowed(member.name):
                continue
            if hashlib.sha256(tar.extractfile(member).read()).hexdigest() != sha256(root / member.name):
                raise ValueError('atlas-code differs from 594c677 archive: ' + member.name)
            checked += 1
    if not checked:
        raise ValueError('atlas-code tree is empty')
    log('verified archived atlas tree', checked, 'files at 594c677')


def stream_daily(path, A, plan, work, guard, targets=None, extra_sources=None):
    light, versions, run_versions, target_rows = {}, Counter(), Counter(), []
    previous, events = '0' * 64, 0
    def journal_targets():
        nonlocal previous, events
        with open(path, 'rb') as f:
            for raw in f:
                e = json.loads(raw)
                seal = e.pop('event_hash')
                if (e['sequence'] != events or e['previous_hash'] != previous or A.digest(e) != seal
                        or e['reason'] != 'compacted target snapshot'):
                    raise ValueError(f'invalid frozen daily event {events}')
                previous, events = seal, events + 1
                yield A.canonical_target(e['target'])
    with open(work / 'candidates.jsonl', 'w', encoding='utf-8', newline='\n') as out:
        for t in journal_targets() if targets is None else targets:
            tid = t['id']
            if tid in light:
                raise ValueError('duplicate frozen target: ' + tid)
            versions[str(t.get('code_version', 'UNKNOWN'))] += 1
            run_versions.update(str(r.get('code_version', 'UNKNOWN')) for r in t.get('runs', []))
            light[tid] = dict(id=tid, kind=t['kind'], ring=t.get('ring'), status=t['status'],
                             campaign_pass=t.get('campaign_pass', 0), budget_round=t.get('budget_round', 0),
                             retired=bool(t.get('retired')), runs=light_runs(t.get('runs', [])),
                             whole=sum(c.get('measurement') == 'whole' for c in t.get('refined_top', [])),
                             gpu_done=sum(bool(r.get('complete')) for r in t.get('runs', [])) >= plan['restarts'],
                             refined=A.campaign.round_refined(t, plan['restarts']))
            # Coverage comes from this daily, not the publication's target metadata.
            target_rows.append({k: v for k, v in t.items() if k in
                ('id', 'kind', 'retired', 'grid_bin', 'grid_step', 'grid_anchor', 'density_period_domains',
                 'density_tier', 'campaign_pass', 'ring', 'usefulness', 'pose_visible_fraction', 'status', 'rev', 'verified')})
            if not t.get('retired'):
                candidates = ranked_candidates(A, t, A.dvd.T_NM / 1000)
                for c in candidates:
                    c['sources'] = sorted(set(c['sources']) | (extra_sources or {}).get(tid, {}).get(c['spec'], set()))
                out.write(json.dumps(dict(id=tid, kind=t['kind'], status=t['status'], shares=t.get('shares'),
                                          candidates=candidates), separators=(',', ':'), allow_nan=False) + '\n')
            if len(light) % 500 == 0:
                guard.check('streaming daily')
                log('daily targets', len(light))
    return light, target_rows, dict(targets=dict(sorted(versions.items())), runs=dict(sorted(run_versions.items())),
                                   events=events, tail_hash=previous)


def compare_export(actual, official):
    """Compare all fields and array positions, including target IDs and winners."""
    import itertools
    count, differences = 0, []
    sentinel = object()
    for left, right in itertools.zip_longest(export_fields(actual), export_fields(official), fillvalue=sentinel):
        count += 1
        if left != right:
            def describe(x):
                if x is sentinel:
                    return 'EOF'
                key, value, kind = x
                return dict(field=key, kind=kind, id=value.get('id') if isinstance(value, dict) else None)
            differences.append(dict(position=count, actual=describe(left), official=describe(right)))
            if len(differences) == 20:
                break
    return dict(status='PASS' if not differences else 'FAIL', compared_fields_and_items=count, differences=differences)


def frozen_extra(args, A, daily, guard):
    """Replay baseline before trusting an extra-journal merge. No live queue rules."""
    copies, source_rows = [], []
    src = args.work / 'extra-src'; src.mkdir(exist_ok=True)
    for role, source in helper_journals(args.extra):
        copy = src / source.name
        shutil.copyfile(source, copy)
        repaired = cut_torn_tail(copy)
        source_rows.append(dict(role=role, source=str(source), copy=str(copy), copy_repair=repaired,
                                bytes=copy.stat().st_size, sha256=sha256(copy), present=True))
        copies.append(copy)
    if not copies:
        raise ValueError('--extra supplied but no journals found')
    # Legacy inputs were not included in the source archive. Reconstitute only
    # their losslessly retained input sections from the frozen official export.
    imports = args.work / 'replay-imports'; imports.mkdir(exist_ok=True)
    legacy = {}
    legacy_keys = {'base_ladder', 'inputs', 'missing_optional_inputs', 'pixel_purity_diagnostics'}
    with open(imports / 'observations.jsonl', 'w', encoding='utf-8', newline='\n') as out:
        for key, value, kind in export_fields(args.snapshot / 'atlas_dvd.json'):
            if key == 'imported_observations' and kind == 'item':
                out.write(json.dumps(value, separators=(',', ':'), ensure_ascii=False) + '\n')
            elif key in legacy_keys:
                if kind == 'array':
                    legacy[key] = []
                elif kind == 'item':
                    legacy[key].append(value)
                else:
                    legacy[key] = value
    (imports / 'legacy_palette_metadata.json').write_text(json.dumps(legacy, ensure_ascii=False), encoding='utf-8')
    log('daily-only merge replay (disk-backed metrics)')
    baseline = args.work / 'daily-only-replay.json'
    result = A.merge.merge([daily], A.dvd, imports, baseline,
                           spill_metrics=True, spill_directory=args.work)
    del result; gc.collect()
    guard.check('daily-only comparison')
    comparison = compare_export(baseline, args.snapshot / 'atlas_dvd.json')
    comparison['peak_working_set_bytes'] = guard.peak_bytes
    (args.work / 'daily-only-comparison.json').write_text(json.dumps(comparison, indent=1), encoding='utf-8')
    if comparison['status'] != 'PASS':
        raise ValueError('daily-only replay differs from official export; see daily-only-comparison.json; extra merge stopped')
    baseline.unlink()
    attribution, machines = {}, {}
    for row, path in zip(source_rows, copies):
        journal = A.journal.Journal(path)
        candidate_count = 0
        for t in journal.targets():
            per_spec = attribution.setdefault(t['id'], {})
            for c in ranked_candidates(A, t, A.dvd.T_NM / 1000):
                per_spec.setdefault(c['spec'], set()).add(row['role']); candidate_count += 1
        machines[row['role']] = dict(events=journal.sequence, targets=len(journal.latest), candidates=candidate_count,
                                     target_ids=list(journal.latest))
    log('merging frozen daily and extra copies')
    result = A.merge.merge([daily, *copies], A.dvd, imports,
                           args.work / 'atlas_dvd.json', spill_metrics=True, spill_directory=args.work)
    del result; gc.collect()
    return A.merge.combined_targets([daily, *copies]), attribution, source_rows, machines, comparison


def build_snapshot(args, guard):
    started = time.time()
    if not args.atlas_code:
        raise ValueError('--snapshot requires --atlas-code (archived 594c677 tree)')
    for path in (args.snapshot, args.atlas_code, args.out, args.work, *args.extra):
        if not allowed(path):
            raise ValueError('excluded path')
        if any(p.casefold() in ('atlas-core', 'atlas-stream') for p in path.parts):
            raise ValueError('frozen build cannot access a live atlas tree')
    for output in (args.out.resolve(), args.work.resolve()):
        for source in (args.snapshot.resolve(), args.atlas_code.resolve(), *(p.resolve() for p in args.extra)):
            if output == source or output in source.parents or source in output.parents:
                raise ValueError('snapshot/code/extra inputs must be separate from output and work')
    if args.reuse_export:
        raise ValueError('--reuse-export is not supported for a frozen build')
    for path, minimum in ((Path('D:/'), 5), (args.work, 15)):
        probe = path
        while not probe.exists():
            probe = probe.parent
        if shutil.disk_usage(probe).free < minimum * 2**30:
            raise ValueError(f'less than {minimum} GiB free at {probe}')
    sources, daily = verify_snapshot(args.snapshot, args.epoch)
    verify_atlas_code(args.atlas_code)
    find_art(args.reader_ref)  # fail before scanning GBs if this ref lacks reader assets
    if not subprocess.check_output(['git', '-C', str(REPO), 'ls-tree', '-r', '--name-only', args.cards_ref,
                                    '--', 'docs/texture-cards']):
        raise ValueError('texture cards not found at ' + args.cards_ref)
    A = Atlas(args.atlas_code.resolve())
    args.work.mkdir(parents=True, exist_ok=True)
    guard.report_path = args.work / 'build-report.json'
    guard.check('frozen build start')
    plan = json.loads((args.snapshot / 'plan.json').read_text(encoding='utf-8'))
    clock = json.loads((args.snapshot / f'campaign-{args.epoch}.json').read_text(encoding='utf-8'))
    status = json.loads((args.snapshot / 'daily-status.json').read_text(encoding='utf-8'))
    targets = attribution = None
    machines, comparison = {}, None
    if args.extra:
        targets, attribution, extra_rows, machines, comparison = frozen_extra(args, A, daily, guard)
        sources.extend(extra_rows)
    else:
        shutil.copyfile(args.snapshot / 'atlas_dvd.json', args.work / 'atlas_dvd.json')
    light, target_rows, versions = stream_daily(daily, A, plan, args.work, guard, targets, attribution)
    merged_versions = versions if args.extra else None
    if args.extra:
        target_versions, run_versions = Counter(), Counter()
        with open(daily, 'rb') as stream:
            for raw in stream:
                t = json.loads(raw)['target']
                target_versions[str(t.get('code_version', 'UNKNOWN'))] += 1
                run_versions.update(str(r.get('code_version', 'UNKNOWN')) for r in t.get('runs', []))
        versions = dict(targets=dict(sorted(target_versions.items())), runs=dict(sorted(run_versions.items())))
    atlas, raw_counts = export_index(args.work / 'atlas_dvd.json', guard)
    # These indexes use daily state even when publication metadata differs.
    atlas['targets'] = target_rows
    counts = {k: raw_counts[k] for k in ('ladder', 'dark', 'order2', 'order3', 'observations',
                                        'imported_observations', 'targets', 'atlas_target_winners')}
    counts.update(compat_singles=raw_counts['singles'], compat_two_line=raw_counts['two_line'],
                  compat_three_line=raw_counts['three_line'])
    # ring-progress is the coordinator's captured summary; control is five hours newer.
    stats = progress_stats(plan, light)
    if not args.extra and any(stats['status_counts'].get(k, 0) != status['statuses'].get(k, 0)
                              for k in set(stats['status_counts']) | set(status['statuses'])):
        raise ValueError('daily status counts disagree with frozen daily-status.json')
    ring_progress = status['rings'] if not args.extra else A.campaign.ring_progress(
        plan, list(light.values()), json.loads((args.snapshot / f'control-{args.epoch}.json').read_text(encoding='utf-8')))
    helper_ids = {tid for role, row in machines.items() if role.startswith('cpu-helper:') for tid in row['target_ids']}
    helper = (dict(journals=sum(role.startswith('cpu-helper:') for role in machines), targets=len(helper_ids),
                   all_restarts_complete=sum(bool(light.get(tid, {}).get('gpu_done')) for tid in helper_ids),
                   refined=sum(bool(light.get(tid, {}).get('refined')) for tid in helper_ids)) if args.extra else None)
    meta = dict(progress=stats, ring_progress=ring_progress, cpu_helper=helper)
    stage = args.out.with_name(args.out.name + '.building')
    if stage.exists():
        shutil.rmtree(stage)
    folder = stage / 'atlas/dvd'; folder.mkdir(parents=True)
    shutil.copyfile(args.work / 'atlas_dvd.json', folder / 'atlas_dvd.json')
    if not args.extra and sha256(folder / 'atlas_dvd.json') != next(r['sha256'] for r in sources if r['role'] == 'atlas_dvd.json'):
        raise ValueError('official export copy hash mismatch')
    winners = {r['id']: r for key in ('atlas_target_winners', 'ladder', 'dark', 'order2', 'order3') for r in atlas[key]}
    cand_stats, cand_counts = build_candidate_tables(args.work / 'candidates.jsonl', folder, winners)
    if set(winners) - set(cand_counts):
        raise ValueError('official winners missing from daily candidate tables')
    counts.update(build_tables(atlas, light, folder, atlas['T_um'], cand_counts))
    counts['candidates'] = cand_stats
    if cand_stats['rank1_not_winner_count']:
        raise ValueError('rank 1 disagrees with official winners: ' + json.dumps(cand_stats))
    del atlas; gc.collect()
    utc = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).isoformat(timespec='seconds')
    snap_time = daily.stat().st_mtime
    cards = texture_cards(stage / 'texture-cards', args.cards_ref)
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    prov = dict(package='disc-neo', version=VERSION, status='preview', media=['dvd'], license='GPL-3.0-or-later',
        epoch=args.epoch, snapshot_utc=utc(snap_time), snapshot_unix=snap_time, built_utc=utc(time.time()),
        merge_code='594c677', code_versions=versions, combined_code_versions=merged_versions,
        snapshot_time_basis='frozen daily file modification time (completion); filename records compaction start',
        compaction_started_utc=utc(int(daily.stem.rsplit('-', 1)[1]) / 1e9),
        encoder_hash=plan['encoder_hash'], plan_hash=clock['plan_hash'],
        control_source_note='control 取自 11-16 09:51',
        ring_progress_source='daily-status.json' if not args.extra else 'daily + extra, with control from 11-16 09:51',
        campaign=dict(started_utc=utc(clock['started']), planned_end_utc=utc(clock['planned_end']),
                      deadline_utc=utc(clock['deadline']), restarts=plan['restarts']),
        export=dict(method='official frozen export, byte-for-byte copy' if not args.extra else '594c677 merge with frozen extra copies',
                    atlas_module_root=str(A.module_root), sha256=sha256(folder / 'atlas_dvd.json'), daily_only_comparison=comparison),
        machines=machines, cpu_helper=helper, progress=stats, ring_progress=ring_progress, counts=counts,
        sources=sources, texture_cards=cards,
        reader_assets=dict(ref=args.reader_ref, commit=subprocess.check_output(
            ['git', '-C', str(REPO), 'rev-parse', args.reader_ref], text=True).strip()),
        extra_candidates={tid: {spec: sorted(roles) for spec, roles in specs.items()} for tid, specs in (attribution or {}).items()},
        builder=dict(script='tools/build_neo.py', commit=head, uncommitted_changes=bool(subprocess.check_output(
            ['git', '-C', str(REPO), 'status', '--porcelain', '--', 'tools/build_neo.py', 'tools/neo_templates'], text=True).strip()),
            python=platform.python_version()))
    values = doc_values(meta, counts, prov); values['_progress'] = stats
    prov['reader'] = write_docs(folder, args.work / 'candidates.jsonl', values, stage, args.reader_ref)
    write_license(stage)
    prov['package_files'] = inventory(stage)
    (stage / 'PROVENANCE.json').write_text(json.dumps(prov, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    problems = check(stage)
    if problems:
        raise ValueError('staging check failed: ' + '\n'.join(problems))
    if args.out.exists():
        old = args.out.with_name(args.out.name + '.previous')
        if old.exists():
            shutil.rmtree(old)
        os.replace(args.out, old)
    os.replace(stage, args.out)
    guard.sample()
    report = dict(status='PASS', mode='B' if args.extra else 'A', out=str(args.out), seconds=round(time.time() - started, 2),
                  peak_working_set_bytes=guard.peak_bytes, working_set_sample_seconds=5, working_set_samples=guard.samples,
                  files=inventory(args.out), counts=counts, progress=stats, ring_progress=ring_progress, values=values,
                  code_versions=versions, daily_only_comparison=comparison)
    (args.work / 'build-report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    (args.work / 'target-progress.json').write_text(json.dumps(light), encoding='utf-8')
    log('PASS frozen mode', report['mode'], counts, 'peak MiB', round(guard.peak_bytes / 2**20))
    return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--atlas', type=Path, default=DEFAULT_ATLAS, help='atlas-core worktree (read-only)')
    ap.add_argument('--snapshot', type=Path, help='verified frozen snapshot directory; never accesses --atlas')
    ap.add_argument('--atlas-code', type=Path, help='root of the archived 594c677 atlas source tree')
    ap.add_argument('--epoch', default='dvd14d-r2')
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--work', type=Path, default=DEFAULT_WORK)
    ap.add_argument('--cards-ref', default='origin/main', help='texture-card git ref')
    ap.add_argument('--reader-ref', help='reader asset git ref (frozen default: 56f2cf7; legacy: --cards-ref)')
    ap.add_argument('--group-mb', type=int, default=200, help='journal bytes merged per group')
    ap.add_argument('--max-snapshot-mb', type=int, default=900, help='refuse to load a larger stripped snapshot')
    ap.add_argument('--ram-floor-mb', type=int, default=1800, help='stop if free RAM falls below this')
    ap.add_argument('--fetch-stale-min', type=int, default=60,
                    help='fetch a GPU journal straight from its worker (read-only scp) when the collected copy is older; 0 = never')
    ap.add_argument('--fetch-timeout', type=int, default=1200, help='seconds per direct fetch attempt')
    ap.add_argument('--extra', type=Path, nargs='*', default=None,
                    help='folders of CPU helper journals merged with the coordinator inputs (pass --extra alone for none)')
    ap.add_argument('--reuse-export', action='store_true', help='reuse --work/atlas_dvd.json and export-meta.json')
    ap.add_argument('--check-only', action='store_true')
    ap.add_argument('--docs-only', action='store_true',
                    help='re-render README/SCHEMA/index.html and PROVENANCE hashes of the staged pack; data files untouched')
    args = ap.parse_args()
    args.reader_ref = args.reader_ref or ('56f2cf7' if args.snapshot else args.cards_ref)
    args.extra = args.extra if args.extra is not None else ([] if args.snapshot else list(DEFAULT_EXTRA))
    if args.snapshot:
        if args.out == DEFAULT_OUT:
            args.out = Path('F:/dp-dev-tmp/neosnap/disc-neo')
        if args.work == DEFAULT_WORK:
            args.work = Path('F:/dp-dev-tmp/neosnap/work')
    else:
        log('WARNING: reading atlas-core is no longer safe; use --snapshot and --atlas-code')
    for p in (args.out, args.work):
        if not allowed(p):
            raise SystemExit(f'refusing path {p}')
    if not args.snapshot:
        ev = (args.atlas / 'evidence' / 'atlas').resolve()
        if args.out.resolve() in (ev, *ev.parents) or ev in args.out.resolve().parents or ev in args.work.resolve().parents:
            raise SystemExit('output and work folders must lie outside the atlas worktree')
    if args.check_only:
        problems = check(args.out)
        print('\n'.join(problems) if problems else 'PASS'); return 1 if problems else 0

    require_onboarding_docs()
    if args.docs_only:
        return docs_only(args)
    low_priority()
    guard = Guard(args.ram_floor_mb)
    if args.snapshot:
        try:
            return build_snapshot(args, guard)
        except (Exception, SystemExit) as exc:
            if args.work.is_dir():
                (args.work / 'build-report.json').write_text(json.dumps(dict(status='FAIL', error=str(exc),
                    peak_working_set_bytes=guard.peak_bytes, working_set_sample_seconds=5,
                    working_set_samples=guard.samples), indent=1), encoding='utf-8')
            raise
    args.work.mkdir(parents=True, exist_ok=True)
    started = time.time()
    A = Atlas(args.atlas.resolve())
    live_stamp = A.provenance.stamp(A.dvd)
    plan = json.loads((ev / 'plan.json').read_text(encoding='utf-8'))
    if live_stamp['code_version'] != plan['code_version'] or live_stamp['encoder_hash'] != plan['encoder_hash']:
        raise SystemExit('atlas code no longer matches the running plan; refusing to export a mixed state')

    if args.reuse_export:
        sources = json.loads((args.work / 'sources.json').read_text(encoding='utf-8'))
        meta = json.loads((args.work / 'export-meta.json').read_text(encoding='utf-8'))
        log('loading previous export'); atlas = json.loads((args.work / 'atlas_dvd.json').read_text(encoding='utf-8'))
    else:
        free = shutil.disk_usage(args.work).free
        need = sum((ev / r).stat().st_size for r in ['manifest.campaign.ready.jsonl'] +
                   [f'collected/{n}' for n in os.listdir(ev / 'collected') if n.endswith('.jsonl')]) * 2.4
        if free < need:
            raise SystemExit(f'need about {need / 2**30:.1f} GiB free in {args.work}, have {free / 2**30:.1f}')
        snap_time = time.time()
        sources = snapshot_sources(ev, args.epoch, args.work / 'src', A, args.fetch_stale_min, args.fetch_timeout, args.extra)
        for r in sources:
            r['snapshot_unix'] = snap_time
        (args.work / 'sources.json').write_text(json.dumps(sources, indent=1), encoding='utf-8')
        atlas, meta = export_atlas(args, A, guard, args.work, sources)
        shutil.rmtree(args.work / 'src')

    snap_time = sources[0].get('snapshot_unix', started)
    clock = json.loads((ev / f'campaign-{args.epoch}.json').read_text(encoding='utf-8'))
    utc = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).isoformat(timespec='seconds')
    counts = dict(ladder=len(atlas['ladder']), dark=len(atlas['dark']), order2=len(atlas['order2']), order3=len(atlas['order3']),
                  observations=len(atlas['observations']), imported_observations=len(atlas['imported_observations']),
                  targets=len(atlas['targets']), atlas_target_winners=len(atlas['atlas_target_winners']),
                  compat_singles=len(atlas['singles']), compat_two_line=len(atlas['two_line']),
                  compat_three_line=len(atlas['three_line']))

    stage = args.out.with_name(args.out.name + '.building')
    if stage.exists():
        shutil.rmtree(stage)
    (stage / 'atlas' / 'dvd').mkdir(parents=True)
    shutil.copyfile(args.work / 'atlas_dvd.json', stage / 'atlas/dvd/atlas_dvd.json')
    target_meta = json.loads((args.work / 'target-progress.json').read_text(encoding='utf-8'))
    winners = {r['id']: r for r in atlas['atlas_target_winners'] + atlas['ladder'] + atlas['dark'] + atlas['order2'] + atlas['order3']}
    cand_stats, cand_counts = build_candidate_tables(args.work / 'candidates.jsonl', stage / 'atlas' / 'dvd', winners)
    log('candidates', {k: v for k, v in cand_stats.items() if k != 'rank1_not_winner'})
    counts.update(build_tables(atlas, target_meta, stage / 'atlas' / 'dvd', atlas['T_um'], cand_counts))
    counts['candidates'] = cand_stats
    del atlas; gc.collect()
    cards = texture_cards(stage / 'texture-cards', args.cards_ref)
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain', '--', 'tools/build_neo.py',
                                          'tools/neo_templates'], text=True).strip())
    prov = dict(
        package='disc-neo', version=VERSION, status='preview', media=['dvd'], license='GPL-3.0-or-later',
        epoch=args.epoch, snapshot_utc=utc(snap_time), snapshot_unix=snap_time, built_utc=utc(time.time()),
        code_version=live_stamp['code_version'], encoder_hash=live_stamp['encoder_hash'],
        plan_hash=clock['plan_hash'],
        campaign=dict(started_utc=utc(clock['started']), planned_end_utc=utc(clock['planned_end']),
                      deadline_utc=utc(clock['deadline']), restarts=plan['restarts']),
        export=dict(method='evidence.atlas.merge.merge() over a compacted snapshot of the coordinator inputs and the CPU helper journals; '
                           'targets merged with evidence.atlas.merge.combined_targets in memory-bounded groups; '
                           'revision numbers replayed against the live refine-input queue as Journal.append does',
                    atlas_module_root=str(A.module_root), refine_input=meta['queue'],
                    reference_stale_marked=meta['reference_stale_marked'], dropped_fields_before_merge=list(HEAVY),
                    snapshot_sha256=meta['snapshot_sha256']),
        machines=meta['machines'], cpu_helper=meta.get('cpu_helper'), progress=meta['progress'], ring_progress=meta['ring_progress'],
        counts=counts, sources=sources, texture_cards=cards,
        builder=dict(script='tools/build_neo.py', commit=head, uncommitted_changes=dirty, python=platform.python_version()))
    values = doc_values(meta, counts, prov)
    values['_progress'] = meta['progress']
    reader = write_docs(stage / 'atlas' / 'dvd', args.work / 'candidates.jsonl', values, stage, args.reader_ref)
    log('reader', reader)
    prov['reader'] = reader
    write_license(stage)
    prov['package_files'] = inventory(stage)
    (stage / 'PROVENANCE.json').write_text(json.dumps(prov, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    problems = check(stage)
    if problems:
        raise SystemExit('staging check failed:\n' + '\n'.join(problems))
    if args.out.exists():
        old = args.out.with_name(args.out.name + '.previous')
        if old.exists():
            shutil.rmtree(old)
        os.replace(args.out, old)
    os.replace(stage, args.out)
    report = dict(out=str(args.out), seconds=round(time.time() - started), files=inventory(args.out), counts=counts,
                  progress=meta['progress'], values=values)
    (args.work / 'build-report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    log('PASS', args.out, f"{sum(r['bytes'] for r in report['files'].values()) / 2**20:.0f} MB")
    return 0


if __name__ == '__main__':
    sys.exit(main())
