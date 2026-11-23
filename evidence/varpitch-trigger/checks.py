"""Run this card's regression checks with isolated test outputs on D:."""
import argparse
import json
import os
import subprocess
import sys
import time

from verify import ROOT, TEMP, setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('selftest', 'python', 'js'))
    parser.add_argument('--js-test')
    args = parser.parse_args()
    setup(False)

    if args.mode in ('python', 'js'):
        # Reuse the PR #29 fixture isolation, browser network guard and cleanup.
        # This script is also named checks.py, so run the prior helper by path.
        import runpy

        prior = ROOT / 'evidence/pr29-merge'
        sys.path.insert(0, str(prior))
        current_verify = sys.modules.pop('verify')
        try:
            previous_verify = __import__('verify')
            previous_verify.TEMP = TEMP
            sys.argv = [str(prior / 'checks.py'), args.mode]
            if args.js_test:
                sys.argv.extend(['--js-test', args.js_test])
            runpy.run_path(sys.argv[0], run_name='__main__')
        finally:
            sys.modules['verify'] = current_verify
        return

    report = TEMP / 'selftest-new.log'
    env = dict(os.environ, DISCPROBE_WORKERS='2', DISCPROBE_PLAIN='1', PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1', DISCPROBE_HOME=str(TEMP / 'selftest-home'),
               LOCALAPPDATA=str(TEMP / 'selftest-localappdata'),
               NODE_OPTIONS='--require=' + str(ROOT / 'evidence/pr29-eval/offline-tests.cjs'))
    start = time.perf_counter()
    with report.open('wb') as log:
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe', 'selftest'],
                             cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    result = dict(exit_code=run.returncode, seconds=time.perf_counter() - start, log=str(report))
    (TEMP / 'selftest-new.json').write_text(json.dumps(result) + '\n', encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
