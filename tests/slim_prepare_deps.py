"""Copy the already installed test runner into scratch, without installing."""
from pathlib import Path
import importlib.util
import shutil
import sys

destination = Path(sys.argv[1]).resolve()
if not destination.is_relative_to(Path('D:/disc-probe-dist').resolve()):
    raise ValueError('test dependencies must stay in the scratch distribution root')
destination.mkdir(parents=True, exist_ok=True)
for name in ('pytest', '_pytest', 'py', 'pluggy', 'iniconfig', 'packaging', 'pygments', 'colorama'):
    spec = importlib.util.find_spec(name)
    if spec is None:
        continue
    source = Path(spec.origin)
    if spec.submodule_search_locations:
        shutil.copytree(source.parent, destination / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', 'tests', 'test', '*b[l]ind*'))
    else:
        shutil.copy2(source, destination / source.name)
print('copied local test dependencies')
