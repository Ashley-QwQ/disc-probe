"""disclab boot: in a process started with DISCPROBE_DISCLAB=<lab folder>, lab drives behave like real ones.

Put this folder first on PYTHONPATH (disclab does it for the processes it starts, and for `python -m disclab web`).
Without DISCPROBE_DISCLAB it does nothing. It patches modules as they load; discprobe's files are not changed:
  discprobe.spti / discprobe.sg  SptiDevice / SgDevice and list_optical_drives: lab drive letters come first
  discprobe.imapi                ImapiDevice: same
  discprobe.burner               adapter(): a lab drive gets the lab recorder
"""
import os
import sys

if os.environ.get("DISCPROBE_DISCLAB"):
    from pathlib import Path

    # Locate the unpacked package even when the child cwd is the lab folder.
    # Its sibling discprobe wins when present; otherwise Python uses the installed wheel.
    _root = str(Path(__file__).resolve().parents[2])
    if _root in sys.path:
        sys.path.remove(_root)
    sys.path.insert(0, _root)
    from disclab.compat import require_discprobe

    try:
        require_discprobe()
    except SystemExit as exc:
        # Python normally ignores exceptions from sitecustomize. Refuse before any
        # device module loads, with just the same sentence as the parent CLI.
        sys.stderr.write(str(exc) + "\n")
        sys.stderr.flush()
        os._exit(1)
    import importlib.abc

    class _DisclabFinder(importlib.abc.MetaPathFinder):
        targets = {"discprobe.spti", "discprobe.sg", "discprobe.imapi", "discprobe.burner"}

        def find_spec(self, name, path, target=None):
            if name not in self.targets:
                return None
            for finder in sys.meta_path:
                if finder is self or not hasattr(finder, "find_spec"):
                    continue
                spec = finder.find_spec(name, path, target)
                if spec is not None:
                    break
            else:
                return None
            loader = spec.loader
            original = loader.exec_module

            def exec_module(module, _original=original):
                _original(module)
                from disclab import hooks
                hooks.patch(module)
            loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, _DisclabFinder())
