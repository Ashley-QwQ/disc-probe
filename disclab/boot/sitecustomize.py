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
    _root = os.environ.get("DISCLAB_ROOT")
    if _root and _root not in sys.path:
        sys.path.append(_root)
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
