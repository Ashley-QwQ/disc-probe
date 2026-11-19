"""Verify a complete portable release ZIP over SSH on x79 or agentbox."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time
import zipfile


REMOTE_SETUP = """\
import hashlib, json, os, pathlib, re, shutil, signal, socket, subprocess, time, urllib.request
root = pathlib.Path.home() / 'dp-linuxpack-test' / cfg['run']
os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[-2:]))
os.nice(19)
"""

REMOTE_PREFLIGHT = """\
free = shutil.disk_usage(root.parent if root.parent.is_dir() else root.parent.parent).free
if free < cfg['required_bytes']:
    raise RuntimeError(f'need {cfg["required_bytes"]} bytes in test directory, have {free}')
unzip = shutil.which('unzip')
if unzip:
    extractor = [unzip]
else:
    busybox = shutil.which('busybox')
    if not busybox or 'unzip' not in subprocess.check_output([busybox, '--list'], text=True).splitlines():
        raise RuntimeError('system unzip is unavailable')
    extractor = [busybox, 'unzip']
root.mkdir(parents=True, exist_ok=False)
(root / 'extractor.json').write_text(json.dumps(extractor), encoding='utf-8')
print(json.dumps(dict(host=os.uname().nodename, machine=os.uname().machine, free_bytes=free,
                      os_release=pathlib.Path('/etc/os-release').read_text(), extractor=extractor,
                      affinity=sorted(os.sched_getaffinity(0)), nice=os.nice(0))))
"""

REMOTE_VERIFY = """\
artifact = root / cfg['file']
unpacked = root / 'Extracted package'
unpacked.mkdir()
temporary = root / 'tmp'
temporary.mkdir()
package = unpacked / cfg['prefix']
with artifact.open('rb') as source:
    assert hashlib.file_digest(source, 'sha256').hexdigest() == cfg['sha256'], 'ZIP SHA-256 mismatch'
print('Archive SHA-256:', cfg['sha256'], flush=True)
extractor = json.loads((root / 'extractor.json').read_text(encoding='utf-8'))
subprocess.run([*extractor, '-q', str(artifact), '-d', str(unpacked)], check=True)
executables = [package / 'start-linux.sh', *sorted((package / 'linux/python/bin').iterdir())]
modes = {str(path.relative_to(package)): oct(path.stat().st_mode & 0o777) for path in executables}
print('Modes immediately after unzip:', json.dumps(modes), flush=True)
assert all(os.access(path, os.X_OK) for path in executables), 'unzip did not restore executable bits'
env = dict(os.environ, HOME=str(unpacked), XDG_CACHE_HOME=str(unpacked / 'cache'),
           XDG_CONFIG_HOME=str(unpacked / 'config'), XDG_RUNTIME_DIR=str(unpacked / 'runtime'),
           TMPDIR=str(temporary), PYTHONNOUSERSITE='1', BROWSER='false',
           OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           NUMEXPR_NUM_THREADS='1', DISCPROBE_WORKERS='1', DISC_PROBE_NO_DRIVES='1')
for key in ('PYTHONHOME', 'PYTHONPATH'):
    env.pop(key, None)
python = [str(package / 'linux/python/bin/python3'), '-X', 'utf8', '-B']

def call(command, *, cwd=package, check=True, timeout=180):
    print('$', json.dumps(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, text=True, encoding='utf-8',
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    print(result.stdout, end='', flush=True)
    if check:
        result.check_returncode()
    return result

call(['bash', str(package / 'start-linux.sh'), '--help'], cwd=unpacked)
call([*python, '-c', '''
import importlib.metadata as metadata, json, pathlib, sys
import cv2, numpy, PIL, scipy
root = pathlib.Path(sys.prefix)
assert root == pathlib.Path.cwd() / 'linux/python'
for mod in (cv2, numpy, PIL, scipy):
    assert pathlib.Path(mod.__file__).is_relative_to(root)
build = json.loads(pathlib.Path('release-build.json').read_text(encoding='utf-8'))['linux']
assert sys.version.split()[0] == build['python']
actual = {name: metadata.version(name) for name in build['dependencies']}
assert actual == build['dependencies']
try:
    metadata.version('opencv-python')
except metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError('GUI OpenCV distribution is present')
print(json.dumps(dict(python=sys.version.split()[0], executable=sys.executable, dependencies=actual)))
'''])
call([*python, '-m', 'discprobe', 'selftest'], timeout=900)
web = [*python, '-m', 'discprobe', 'webui']
status = call([*web, 'status'], check=False, timeout=15)
lifecycle = not (status.returncode == 2 and 'unrecognized arguments: status' in status.stdout)
if not lifecycle:
    stop = call([*web, 'stop'], check=False, timeout=15)
    assert stop.returncode == 2 and 'unrecognized arguments: stop' in stop.stdout
    print('CLI status/stop unavailable; verifying foreground startup and SIGINT shutdown.', flush=True)
launch = [*web, '--local-only', '--port', '0']
print('$', json.dumps(launch), flush=True)
with (root / 'web.log').open('w', encoding='utf-8') as log:
    server = subprocess.Popen(launch, cwd=package, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(300):
            stdout = (root / 'web.log').read_text(encoding='utf-8')
            url = re.search(r'http://127\\.0\\.0\\.1:\\d+/home/', stdout)
            if url:
                break
            if server.poll() is not None:
                raise RuntimeError('webui exited before listening: ' + stdout)
            time.sleep(0.2)
        else:
            raise RuntimeError('webui startup timed out')
        for suffix in ('/home/', '/api/version'):
            with urllib.request.urlopen(url.group().removesuffix('/home/') + suffix, timeout=15) as response:
                payload = response.read()
                assert response.status == 200 and payload
                print(f'GET {suffix}: {response.status} ({len(payload)} bytes)', flush=True)
        if lifecycle:
            call([*web, 'status'], timeout=15)
            call([*web, 'stop'], timeout=15)
        else:
            server.send_signal(signal.SIGINT)
        assert server.wait(timeout=20) == 0, 'webui did not exit cleanly'
        with socket.socket() as client:
            client.settimeout(3)
            port = int(url.group().split(':')[2].split('/')[0])
            assert client.connect_ex(('127.0.0.1', port)) != 0, 'webui still listening'
        print('WebUI listener closed.', flush=True)
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
print('PASS', flush=True)
"""

REMOTE_CLEANUP = """\
for directory in ('Extracted package', 'tmp'):
    path = root / directory
    if path.exists():
        assert path.resolve().parent == root.resolve()
        shutil.rmtree(path)
(root / cfg['file']).unlink(missing_ok=True)
print('Removed uploaded and extracted package; retained logs in', root)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('x79', 'agentbox'), required=True)
    parser.add_argument('--zip', dest='artifact', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    out = args.out.resolve()
    if any('b' + 'lind' in part.casefold() for path in (artifact, out) for part in path.parts):
        parser.error('excluded input or output path')
    if not re.fullmatch(r'disc-probe-[0-9A-Za-z.-]+-full\.zip', artifact.name) or not artifact.is_file():
        parser.error('provide a release disc-probe-<version>-full.zip')
    with zipfile.ZipFile(artifact) as archive:
        size = 0
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if (not parts or parts[0] != artifact.stem or '..' in parts
                    or '\\' in member.filename or ':' in member.filename
                    or any('b' + 'lind' in part.casefold() for part in parts)
                    or stat.S_ISLNK(member.external_attr >> 16)):
                parser.error('ZIP contains a linked or excluded entry')
            size += member.file_size
        if f'{artifact.stem}/linux/python/bin/python3' not in archive.namelist():
            parser.error('ZIP needs the portable Linux runtime')
    with artifact.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    run = f'run-{time.time_ns()}'
    cfg = dict(run=run, file=artifact.name, prefix=artifact.stem, sha256=digest,
               required_bytes=artifact.stat().st_size + size + 512 * 2**20)
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', args.host, 'python3', '-']
    destination = f'{args.host}:dp-linuxpack-test/{run}/'

    def remote(stage, code):
        script = f'cfg = {cfg!r}\n' + REMOTE_SETUP + code
        done = subprocess.run(ssh, input=script, encoding='utf-8', capture_output=True, timeout=1500)
        (out / f'{stage}.log').write_text(done.stdout + done.stderr, encoding='utf-8')
        done.check_returncode()

    result = dict(status='FAIL', host=args.host, remote_root=f'~/dp-linuxpack-test/{run}', input=cfg)
    prepared = False
    try:
        remote('preflight', REMOTE_PREFLIGHT)
        prepared = True
        subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                        str(artifact), destination], check=True, timeout=900)
        remote('verify', REMOTE_VERIFY)
        result['status'] = 'PASS'
    except (subprocess.SubprocessError, OSError) as exc:
        result['error'] = str(exc)
        raise
    finally:
        try:
            if prepared:
                # Keep the verification transcript alongside the remote server log.
                transcript = out / 'verify.log'
                if transcript.is_file():
                    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                    str(transcript), destination + 'verify.log'], check=True, timeout=30)
        except (subprocess.SubprocessError, OSError) as exc:
            result.update(status='FAIL', log_copy_error=str(exc))
            raise
        finally:
            try:
                if prepared:
                    remote('cleanup', REMOTE_CLEANUP)
            except (subprocess.SubprocessError, OSError) as exc:
                result.update(status='FAIL', cleanup_error=str(exc))
                raise
            finally:
                (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"{args.host}: {result['status']} ({out})")


if __name__ == '__main__':
    main()
