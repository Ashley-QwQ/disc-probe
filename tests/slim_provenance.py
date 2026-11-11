"""Record source/input provenance and reject production SciPy imports."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ROOT, ARTIFACTS, walk


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    base = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    protected = 'discprobe/scsi.py'
    before = subprocess.run(['git', '-C', str(ROOT), 'show', f'HEAD:{protected}'], check=True, capture_output=True).stdout
    after = (ROOT / protected).read_bytes()
    before_blob = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', f'HEAD:{protected}'], check=True, capture_output=True, text=True).stdout.strip()
    after_blob = subprocess.run(['git', '-C', str(ROOT), 'hash-object', '--path=' + protected, protected], check=True, capture_output=True, text=True).stdout.strip()
    imports, hashes = [], {}
    for folder in ('discprobe', 'tools'):
        for path in walk(ROOT / folder):
            if path.suffix != '.py':
                continue
            source = path.read_bytes()
            hashes[str(path.relative_to(ROOT)).replace('\\', '/')] = digest(source)
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    if name == 'scipy' or name.startswith('scipy.'):
                        imports.append(dict(path=str(path.relative_to(ROOT)), line=node.lineno, module=name))
    identical = before_blob == after_blob
    info = dict(base_commit=base, protected=dict(path=protected, head_lf_sha256=digest(before), worktree_raw_sha256=digest(after),
                                               head_blob=before_blob, worktree_blob=after_blob, identical=identical,
                                               line_endings='Git HEAD is LF; pre-existing Windows worktree uses CRLF'),
                production_scipy_imports=imports, source_sha256=hashes)
    (ARTIFACTS / 'provenance.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    exclusions = [':(exclude,icase,glob)**/*b[l]ind*', ':(exclude,icase,glob)**/*b[l]ind*/**']
    found = subprocess.run(['git', '-C', str(ROOT), 'grep', '-n', '-i', 'scipy', 'HEAD', '--', '.', *exclusions], capture_output=True, text=True, encoding='utf-8')
    (ARTIFACTS / 'scipy-uses-before.txt').write_text(found.stdout, encoding='utf-8')
    print(json.dumps(dict(base=base, scsi_unchanged=identical, production_scipy_imports=imports)))
    if imports or not identical:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
