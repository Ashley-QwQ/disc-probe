"""Run mandated checks once, serially, with logs and F: temporary storage."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TEMP = Path('F:/dp-dev-tmp/pr29eval/checks')
BLOCKED = ''.join(('b', 'l', 'i', 'n', 'd'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--only', choices=('all', 'selftest', 'python', 'js'), default='all')
    ap.add_argument('--js-test', help='Rerun one named JS file, retaining the first-run log')
    args = ap.parse_args()
    free = {d: shutil.disk_usage(d).free for d in ('D:/', 'F:/')}
    if min(free.values()) < 5 * 1024 ** 3:
        raise SystemExit('STOP: disk below 5 GiB')
    TEMP.mkdir(parents=True, exist_ok=True)
    logs = OUT / 'checks'
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP),
               PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NODE_OPTIONS='--require=' + str(OUT / 'offline-tests.cjs'))
    for key in ('AFTERBURN_TEST_ROOT', 'BURN_CANCEL_TEST_ROOT', 'RW_DISCS_TEST_ROOT',
                'W245_TEST_ROOT', 'BRAND_TEST_TEMP', 'BRAND_MIXED_OUTPUT'):
        env[key] = str(TEMP / key.lower())
    commands = []
    if args.only in ('all', 'selftest'):
        commands.append(('selftest', [sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe', 'selftest']))
    if args.only in ('all', 'python'):
        files = ['tests/test_geo_integration.py', 'tests/test_geo_progress.py',
                 'tests/test_geo_unsteady.py', 'tests/test_geo_varpitch.py']
        commands.append(('pytest_geo', [sys.executable, '-B', '-X', 'utf8', '-m', 'pytest', '-n', '2',
                                       '--basetemp=' + str(TEMP / 'pytest'), '-q', *files]))
    if args.only in ('all', 'js'):
        with os.scandir(ROOT / 'tests') as entries:
            files = sorted(e.name for e in entries if BLOCKED not in e.path.lower()
                           and e.name.startswith('test_') and e.name.endswith('.mjs'))
        if args.js_test:
            if args.js_test not in files:
                raise SystemExit('Unknown allowed JS test')
            files = [args.js_test]
        commands.extend((Path(f).stem, ['node', 'tests/' + f]) for f in files)
    rows = []
    for name, command in commands:
        if min(shutil.disk_usage(d).free for d in ('D:/', 'F:/')) < 5 * 1024 ** 3:
            raise SystemExit('STOP: disk below 5 GiB during checks')
        start = time.monotonic()
        log = logs / (name + ('_retry' if args.js_test else '') + '.log')
        with log.open('w', encoding='utf-8') as f:
            f.write('COMMAND: ' + subprocess.list2cmdline(command) + '\n')
            f.flush()
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
            try:
                rc = child.wait(timeout=600 if name in ('selftest', 'pytest_geo') else 180)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                child.wait()
                rc = 'TIMEOUT'
        row = dict(name=name, exit_code=rc, seconds=round(time.monotonic() - start, 3),
                   command=subprocess.list2cmdline(command), log=str(log.relative_to(ROOT)))
        rows.append(row)
        print(json.dumps(row), flush=True)
        with (logs / ('results_' + args.only + ('_retry' if args.js_test else '') + '.csv')).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerows(rows)
    (logs / ('disk_' + args.only + '.json')).write_text(json.dumps(dict(before=free, after={d: shutil.disk_usage(d).free for d in free}), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
