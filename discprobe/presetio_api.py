"""Small HTTP adapter; interchange itself lives in presets.py."""
import json
from pathlib import Path

from . import presets, zh


def local(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("choose a DP preset")
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".json" or not path.is_file():
        raise ValueError("preset must be a JSON file inside the workspace")
    return path


def listing(root):
    root = Path(root).resolve()
    items = []
    for path in sorted((root / "presets").glob("*.json")):
        if not path.resolve().is_relative_to(root):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data.get("preset"), dict):
                items.append(dict(path=path.relative_to(root).as_posix(), name=data["preset"].get("displayName", path.stem)))
        except (OSError, ValueError, AttributeError):
            continue
    return dict(version=1, presets=items)


def handle(root, payload):
    if not isinstance(payload, dict):
        raise ValueError("preset request must be an object")
    operation = payload.get("operation")
    if operation in ("preview", "import"):
        filename = payload.get("filename", "disc-presets.json")
        if not isinstance(filename, str) or len(filename) > 1024:
            raise ValueError("invalid filename")
        folder = (Path(root) / "presets").resolve()
        if not folder.is_relative_to(Path(root).resolve()):
            raise ValueError("presets folder must stay inside workspace")
        result = presets.import_file(payload.get("text"), filename, folder,
            selected=payload.get("selected"), dry_run=operation == "preview", media=payload.get("media"))
        for row in result["entries"]:
            row["issues_zh"] = [zh.TEXT.get(s, s) for s in row["issues"]]
        return result
    if operation == "export":
        path = local(root, payload.get("path"))
        install = payload.get("install", False)
        if type(install) is not bool:
            raise ValueError("install must be a boolean")
        # HTTP clients can select the workspace's temporary/custom DIS file, never arbitrary paths.
        target = payload.get("dis_presets")
        if target is not None:
            if not isinstance(target, str) or Path(target).is_absolute():
                raise ValueError("custom DIS target must be relative to the workspace")
            target = (Path(root) / target).resolve()
            if not target.is_relative_to(Path(root).resolve()) or target.suffix != ".json":
                raise ValueError("custom DIS target must be inside the workspace")
        return presets.export_file(path, install=install, dis_presets=str(target) if target else None)
    raise ValueError("unknown preset operation")
