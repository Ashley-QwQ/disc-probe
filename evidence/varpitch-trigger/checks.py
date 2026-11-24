"""Run this card's regression checks with isolated test outputs on D:."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from verify import ROOT, TEMP, setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('selftest', 'python'))
    args = parser.parse_args()
    setup(False)
    guard = Path(__file__).resolve().with_name('no_browser')
    os.environ['PYTHONPATH'] = os.pathsep.join((str(guard), str(ROOT)))
    os.environ.pop('NODE_OPTIONS', None)

    if args.mode == 'python':
        os.environ['PYTEST_ADDOPTS'] = ' '.join(filter(None, (
            os.environ.get('PYTEST_ADDOPTS', ''),
            '--deselect=tests/test_geo_progress.py::test_web_progress_bounds',
            '--deselect=tests/test_geo_unsteady.py::test_page_calibrate_arguments',
        )))
        # Reuse the PR #29 fixture isolation and cleanup.
        # This script is also named checks.py, so run the prior helper by path.
        import runpy

        prior = ROOT / 'evidence/pr29-merge'
        sys.path.insert(0, str(prior))
        current_verify = sys.modules.pop('verify')
        try:
            previous_verify = __import__('verify')
            previous_verify.TEMP = TEMP
            sys.argv = [str(prior / 'checks.py'), args.mode]
            runpy.run_path(sys.argv[0], run_name='__main__')
        finally:
            sys.modules['verify'] = current_verify
        return

    report = TEMP / 'selftest-round2-no-browser.log'
    env = dict(os.environ, DISCPROBE_WORKERS='2', DISCPROBE_PLAIN='1', PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1', DISCPROBE_HOME=str(TEMP / 'selftest-home'),
               LOCALAPPDATA=str(TEMP / 'selftest-localappdata'))
    start = time.perf_counter()
    with report.open('wb') as log:
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe', 'selftest'],
                             cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    result = dict(exit_code=run.returncode, seconds=time.perf_counter() - start, log=str(report))
    (TEMP / 'selftest-round2-no-browser.json').write_text(json.dumps(result) + '\n', encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
