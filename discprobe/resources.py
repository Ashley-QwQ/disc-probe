"""Runtime helpers also carried inside a pip installation."""
from pathlib import Path


def tool(name):
    here = Path(__file__).resolve().parent
    packaged = here / '_tools' / name
    return packaged if packaged.is_file() else here.parent / 'tools' / name
