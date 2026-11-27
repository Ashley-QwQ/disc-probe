"""The sole old numerical backend. Optional and used only by the harness.

No production code imports this module. A missing SciPy skips oracle tests.
"""
import importlib.util

AVAILABLE = importlib.util.find_spec('scipy') is not None
if AVAILABLE:
    from scipy.ndimage import gaussian_filter, maximum_filter, uniform_filter
    from scipy.optimize import least_squares, minimize
    from scipy.signal import fftconvolve
    from scipy.stats import f

