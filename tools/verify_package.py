"""Verify an extracted/installed release, using this interpreter, outside the checkout."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import threading
import time
import urllib.request


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--artifact', type=Path, required=True)
    ap.add_argument('--expected-root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='1.0.0-alpha')
    ap.add_argument('--photo', type=Path)
    ap.add_argument('--photo-design', default='spoke30')
    a = ap.parse_args()
    a.artifact = a.artifact.resolve()
    a.expected_root = a.expected_root.resolve()
    if a.photo:
        a.photo = a.photo.resolve()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    os.chdir(out)
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    python = [sys.executable, '-X', 'utf8', '-B']
    result = dict(status='RUNNING', platform=platform.platform(), python=sys.version,
                  executable=sys.executable, artifact=dict(file=a.artifact.name, size=a.artifact.stat().st_size,
                  sha256=digest(a.artifact)), checks=[])

    def save():
        (out / 'proof.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def command(name, argv, timeout=1800):
        start = time.monotonic()
        with (out / (name + '.log')).open('w', encoding='utf-8') as log:
            r = subprocess.run(argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        result['checks'].append(dict(name=name, exit_code=r.returncode, seconds=round(time.monotonic()-start,3),
                                      log=name+'.log', sha256=digest(out/(name+'.log'))))
        save()
        if r.returncode:
            raise RuntimeError(f'{name} failed: {r.returncode}')
        return (out/(name+'.log')).read_text(encoding='utf-8')

    try:
        import discprobe
        from discprobe import pcal
        import cv2, scipy, numpy, PIL
        cv2.setNumThreads(1)
        package = Path(discprobe.__file__).resolve()
        assert package.is_relative_to(a.expected_root.resolve()), str(package)
        result['module'] = str(package)
        result['dependencies'] = {n:metadata.version(n) for n in ('numpy','Pillow','scipy','opencv-python')}
        result['imports'] = {m.__name__:str(Path(m.__file__).resolve()) for m in (pcal,cv2,scipy,numpy,PIL)}
        candidates = [package.parent/'_release.json', package.parent.parent/'release-build.json']
        source = next(p for p in candidates if p.is_file())
        result['provenance'] = json.loads(source.read_text(encoding='utf-8'))
        if os.name == 'nt' and (Path(sys.executable).parent/'disc-probe.exe').is_file():
            cli = [str(Path(sys.executable).parent/'disc-probe.exe')]
        elif os.name != 'nt':
            cli = [str(Path(sys.executable).parent/'disc-probe')]
        else:
            cli = [*python, '-m', 'discprobe']
        command('help', [*cli, '--help'], 60)
        version = json.loads(command('version', [*cli, 'version', '--json'], 60))
        assert version['core_version'] == a.version
        result['version'] = version
        # Exercise the actual CLI parser/service with an explicit empty device
        # provider. No device names are enumerated and no drive is ever opened.
        bootstrap = "from discprobe import guide; guide.optical_drives=lambda: []; import sys,runpy; sys.argv=['discprobe','webui','--local-only','--port','0']; runpy.run_module('discprobe',run_name='__main__')"
        log = (out/'web.log').open('w',encoding='utf-8')
        server = subprocess.Popen([*python, '-u', '-c', bootstrap], cwd=out, env=env,
                                  stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8')
        lines = queue.Queue()
        def reader():
            for line in server.stdout:
                lines.put(line)
        thread = threading.Thread(target=reader,daemon=True); thread.start()
        try:
            url = lines.get(timeout=45).strip()
            assert url.startswith('http://127.0.0.1:') and url.endswith('/home/'), url
            result['web'] = dict(url=url, localhost_only=True, no_drives='injected empty provider', requests=[])
            base = url.removesuffix('/home/')
            def get(path):
                with urllib.request.urlopen(base+path, timeout=30) as response:
                    body=response.read()
                    assert response.status==200
                    result['web']['requests'].append(dict(path=path,status=response.status,size=len(body),sha256=hashlib.sha256(body).hexdigest()))
                    return body
            assert json.loads(get('/api/version')) == version
            lobby=get('/home/'); (out/'lobby.html').write_bytes(lobby)
            assert b'<html' in lobby.lower()
            asset=get('/home/design/editor-ui.mjs'); assert asset
            state=json.loads(get('/api/state')); assert state['drives']==[]
            result['web']['state']=state
            # Save and reopen a known design through the packaged backend. The
            # returned .npy is inspected from this verification workspace.
            packed=b'\x55'*(6000*6000//8)
            req=urllib.request.Request(base+'/api/design',data=packed,headers={'Content-Type':'application/octet-stream'})
            with urllib.request.urlopen(req, timeout=45) as response:
                saved=json.loads(response.read()); assert response.status==200
            design_path=(out/saved['design_npy']).resolve()
            assert design_path.is_relative_to(out)
            reopened=numpy.load(design_path)
            assert reopened.shape==(6000,6000) and float(reopened.mean())==0.5
            result['web']['save_reopen']=dict(response=saved,shape=list(reopened.shape),sha256=digest(design_path))
        finally:
            server.terminate()
            try: server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill(); server.wait(timeout=10)
            thread.join(timeout=2); log.close()
        command('selftest', [*cli, 'selftest'])
        if a.photo:
            from PIL import Image, ImageOps
            with Image.open(a.photo) as image:
                rgb=numpy.asarray(ImageOps.exif_transpose(image).convert('RGB'))
            design=pcal.DESIGNS[a.photo_design]()
            start=time.monotonic()
            with (out/'photo.log').open('w',encoding='utf-8') as photo_log:
                diagnostics=pcal.read_photo(rgb,design,log=lambda *s: print(*s,file=photo_log,flush=True))
            result['photo']=dict(input=str(a.photo),sha256=digest(a.photo),size=a.photo.stat().st_size,
                                 scope='packaging execution only; measurement accuracy not assessed',
                                 shape=list(rgb.shape),design=design.name,seconds=round(time.monotonic()-start,3),
                                 reader_sha256=digest(Path(pcal.__file__)),status=diagnostics.get('status'),diagnostics=diagnostics)
        result['status']='PASS'
    except BaseException as exc:
        result['status']='FAIL'; result['error']=repr(exc); raise
    finally:
        save()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
