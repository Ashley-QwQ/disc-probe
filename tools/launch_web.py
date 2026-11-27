"""Deprecated compatibility entry point. Use python -m discprobe webui --open."""
from __future__ import annotations

from pathlib import Path
import sys

# A direct script must also work with a regular Python in the source package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from discprobe.__main__ import main as core_main
    return core_main(["webui", "--open", *sys.argv[1:]])


if __name__ == '__main__':
    main()
