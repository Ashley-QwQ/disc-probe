"""Independent specification checks that also run in the SciPy-free pack."""
import itertools
import math
import numpy as np
from discprobe import numerics as n


def test_reflect_maximum_definition():
    for shape in ((1,), (2,), (3,), (2, 2)):
        for values in itertools.product((-2, 0, 3), repeat=math.prod(shape)):
            a = np.array(values).reshape(shape)
            for width in (1, 2, 3, 5):
                p = np.pad(a, [(width // 2, (width - 1) // 2)] * a.ndim, mode='symmetric')
                want = np.empty_like(a)
                for index in np.ndindex(shape):
                    want[index] = p[tuple(slice(i, i + width) for i in index)].max()
                assert np.array_equal(n.maximum_filter(a, width), want)


def test_gaussian_preserves_constant_and_dtype():
    for dtype in (np.float32, np.float64):
        for sigma in (0, 1, 1.5, 5, 6, 12, 15):
            a = np.ones((4, 7), dtype=dtype)
            b = n.gaussian_filter(a, sigma)
            assert b.dtype == a.dtype
            assert np.max(np.abs(a - b)) < 5 * np.finfo(dtype).eps


def test_convolution_matches_integer_definition():
    a = np.arange(20).reshape(4, 5)
    b = np.array([[1, -2], [3, 4]])
    full = np.zeros((5, 6))
    for i, j in np.ndindex(a.shape):
        full[i:i + 2, j:j + 2] += a[i, j] * b
    assert np.max(np.abs(n.fftconvolve(a, b) - full[:4, :5])) < 1e-12


def test_linear_solution_and_rank_detection():
    A = np.array([[1., 0], [0, 2], [1, 2]])
    expected = np.array([3., -2])
    sol = n.least_squares(lambda x: A @ (x - expected), [0., 0.], jac=lambda x: A)
    assert np.max(np.abs(sol.x - expected)) < 1e-10
    assert sol.certificate['stationary']
    certificate = n.solution_certificate(lambda x: np.array([x.sum() - 1]), [.5, .5])
    assert not certificate['identifiable']


def test_f_survival_exact_df_two():
    # F(2,2) has survival 1/(1+x), an independent algebraic oracle.
    for x in (0, 1e-12, .1, 1, 10, 1e12):
        assert abs(n.f_sf(x, 2, 2) - 1 / (1 + x)) <= 2e-16

