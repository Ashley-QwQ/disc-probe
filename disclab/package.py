"""Assemble the standalone zip, without Python, disc-probe or experiment output."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import zipfile


def build(output):
    package = Path(__file__).resolve().parent
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    roots = [*package.glob("*.py"), *package.glob("*.md"), package / "LICENSE"]
    for folder in ("boot", "data", "examples", "tests", "web"):
        for base, dirs, names in os.walk(package / folder):
            dirs[:] = sorted(n for n in dirs if "b" + "lind" not in n.casefold() and n != "__pycache__")
            roots.extend(Path(base) / n for n in sorted(names) if "b" + "lind" not in n.casefold())
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(set(roots)):
            if (not any("b" + "lind" in p.casefold() for p in source.parts)
                    and source.is_file() and "__pycache__" not in source.parts
                    and (source.name == "LICENSE" or source.suffix in {".py", ".md", ".npz", ".pgm", ".json", ".ps1", ".sh",
                                                                     ".html", ".css", ".js", ".mjs", ".webp", ".woff2", ".txt", ".ico", ".png"})):
                archive.write(source, source.relative_to(package.parent).as_posix())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(build(parser.parse_args().output))
