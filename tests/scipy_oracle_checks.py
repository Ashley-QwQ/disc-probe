"""Optional numerical oracle checks. No application depends on SciPy."""
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec('scipy') is None, reason='optional SciPy oracle absent')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import equivalence_scipy as old
from discprobe import numerics as new


def gaussian_bound(a, sigma):
    # Two implementations: coefficient formation + double summation + per-pass cast.
    r = int(4 * sigma + .5)
    u = np.finfo(float).eps / 2
    gamma = lambda k: k * u / (1 - k * u)
    v = np.finfo(a.dtype).eps / 2
    return a.ndim * (2 * gamma(4 * (2 * r + 1) + 32) + 2 * v) * max(float(np.max(np.abs(a))), np.finfo(a.dtype).tiny)


def fft_bound(a, b):
    # Conditional radix-2 FFT model, 64 real roundings per stage.
    shape = [1 << (x + y - 2).bit_length() for x, y in zip(a.shape, b.shape)]
    stages = sum(int(math.log2(v)) for v in shape)
    # Both pinned libraries can preserve float32 FFTs. Mixed input types must
    # include the precision of each operand before multiplication promotes it.
    # SciPy transforms mixed-dtype operands at their individual precisions.
    # In particular float64 * float32 is not an all-float64 FFT pipeline.
    u = max(np.finfo(np.result_type(a.dtype, np.float32)).eps,
            np.finfo(np.result_type(b.dtype, np.float32)).eps) / 2
    k = 64 * (3 * stages + 1)
    gamma = k * u / (1 - k * u)
    return 2 * gamma * float(np.sum(np.abs(a), dtype=float)) * float(np.sum(np.abs(b), dtype=float))


def test_exhaustive_maximum_oracle():
    for shape in ((1,), (2,), (3,), (2, 2)):
        for values in itertools.product((-1, 0, 1), repeat=math.prod(shape)):
            a = np.array(values, dtype=np.int16).reshape(shape)
            for width in (1, 2, 3, 4, 5, 7):
                assert new.maximum_filter(a, width).tobytes() == old.maximum_filter(a, width).tobytes()
    for values in itertools.product((-1., 0., -0.), repeat=5):
        a = np.array(values)
        for width in (2, 3, 4, 5, 7):
            assert new.maximum_filter(a, width).tobytes() == old.maximum_filter(a, width).tobytes()


def test_randomized_filters_oracle():
    rng = np.random.default_rng(20261111)
    for dtype in (np.float32, np.float64):
        for shape in ((1, 1), (2, 7), (31, 45), (3, 4, 2)):
            a = rng.normal(size=shape).astype(dtype)
            for sigma in (1, 1.5, 5, 6, 12, 15):
                assert np.max(np.abs(new.gaussian_filter(a, sigma) - old.gaussian_filter(a, sigma))) <= gaussian_bound(a, sigma)
            for width in (2, 3, 13):
                assert new.maximum_filter(a, width).tobytes() == old.maximum_filter(a, width).tobytes()
            b = rng.normal(size=tuple(min(5, n) for n in shape)).astype(dtype)
            assert np.max(np.abs(new.fftconvolve(a, b) - old.fftconvolve(a, b, 'same'))) <= fft_bound(a, b)


def test_nelder_mead_iteration_path_on_smooth_objective():
    cost = lambda x: float(np.sum((x - np.arange(len(x))) ** 2))
    opts = dict(maxiter=3000, xatol=1e-3, fatol=1e-6)
    a = old.minimize(cost, np.ones(8), method='Nelder-Mead', options=opts)
    b = new.minimize(cost, np.ones(8), options=opts)
    assert a.x.tobytes() == b.x.tobytes()
    assert a.fun == b.fun and a.nfev == b.nfev


def test_f_sf_oracle():
    for a, b in itertools.product((1, 2, 3, 7, 30), (1, 2, 5, 28, 100)):
        for x in (0, 1e-8, .1, 1, 10, 100, 1e8):
            assert abs(new.f_sf(x, a, b) - old.f.sf(x, a, b)) < 2e-13
