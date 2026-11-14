"""Assemble the standalone zip, without Python, disc-probe or experiment output."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


def build(output):
    package = Path(__file__).resolve().parent
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    roots = [*package.glob("*.py"), *package.glob("*.md"), package / "LICENSE"]
    for folder in ("boot", "data", "examples", "tests", "web"):
        roots.extend((package / folder).rglob("*"))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(set(roots)):
            if (source.is_file() and "__pycache__" not in source.parts
                    and (source.name == "LICENSE" or source.suffix in {".py", ".md", ".npz", ".pgm", ".json", ".ps1", ".sh",
                                                                     ".html", ".css", ".js", ".webp", ".woff2", ".txt"})):
                archive.write(source, source.relative_to(package.parent).as_posix())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(build(parser.parse_args().output))
