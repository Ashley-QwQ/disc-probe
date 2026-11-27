"""Small, deliberately restricted numerical operations used by disc-probe.

Only the signatures exercised by the application are supported. See EQUIVALENCE.md
for domains, rounding assumptions and the limits of solver certification.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import math
from types import SimpleNamespace
import warnings

import numpy as np


def _sizes(value, ndim):
    return [value] * ndim if np.isscalar(value) else list(value)


def gaussian_filter(input, sigma, *, mode="reflect", truncate=4.0):
    """Order-zero, axis-ordered, double-accumulated separable Gaussian."""
    if mode != "reflect":
        raise ValueError("only half-sample reflect is supported")
    out = np.array(input, copy=True)
    if out.dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise TypeError("Gaussian input must be float32 or float64")
    for axis, sd in enumerate(_sizes(sigma, out.ndim)):
        if sd <= 1e-15:
            continue
        radius = int(truncate * float(sd) + 0.5)
        x = np.arange(-radius, radius + 1)
        k = np.exp(-0.5 / (float(sd) * float(sd)) * x ** 2)
        k /= k.sum()
        pads = [(0, 0)] * out.ndim
        pads[axis] = (radius, radius)
        padded = np.pad(out, pads, mode="symmetric")
        out = np.apply_along_axis(lambda row: np.convolve(row, k, "valid"), axis, padded).astype(out.dtype)
    return out


def maximum_filter(input, size):
    """Full rectangular, origin-zero, reflect maximum for non-NaN real inputs."""
    out = np.asarray(input)
    if np.isnan(out).any():
        raise ValueError("NaN maximum-filter behaviour is undefined; non-NaN input required")
    for axis, width in enumerate(_sizes(size, out.ndim)):
        width = int(width)
        if width < 1:
            raise ValueError("filter size must be positive")
        if width == 1:
            continue
        pads = [(0, 0)] * out.ndim
        pads[axis] = (width // 2, (width - 1) // 2)
        a = np.pad(out, pads, mode="symmetric")
        # Blocked van Herk maxima: linear work, bounded temporary storage.
        a = np.moveaxis(a, axis, -1)
        n = a.shape[-1]
        padded = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(0, (-n) % width)], mode="edge")
        blocks = padded.reshape(*a.shape[:-1], -1, width)
        prefix = np.maximum.accumulate(blocks, axis=-1).reshape(padded.shape)
        suffix = np.maximum.accumulate(blocks[..., ::-1], axis=-1)[..., ::-1].reshape(padded.shape)
        length = out.shape[axis]
        result = np.maximum(suffix[..., :length], prefix[..., width - 1:width - 1 + length])
        # Equal nonzero finite values have the same bits. Signed zero is the
        # exception: the reference's MAXLIST retains the last equal maximum.
        if np.issubdtype(a.dtype, np.floating) and (result == 0).any():
            last_zero = np.maximum.accumulate(np.where(a == 0, np.arange(n), -1), axis=-1)
            index = np.maximum(0, last_zero[..., width - 1:width - 1 + length])
            selected = np.take_along_axis(a, index, axis=-1)
            result = np.where(result == 0, selected, result)
        out = np.moveaxis(result, -1, axis)
    return out


def fftconvolve(a, b, mode="same"):
    """Real, zero-padded N-D linear convolution, cropped relative to a."""
    a, b = np.asarray(a), np.asarray(b)
    if mode != "same" or a.ndim != b.ndim:
        raise ValueError("only same-mode real arrays of equal rank are supported")
    if np.iscomplexobj(a) or np.iscomplexobj(b):
        raise TypeError("real input required")
    full = tuple(x + y - 1 for x, y in zip(a.shape, b.shape))
    shape = tuple(1 << (n - 1).bit_length() for n in full)
    axes = tuple(range(a.ndim))
    c = np.fft.irfftn(np.fft.rfftn(a, shape, axes=axes) * np.fft.rfftn(b, shape, axes=axes), shape, axes=axes)
    crop = tuple(slice((m - 1) // 2, (m - 1) // 2 + n) for n, m in zip(a.shape, b.shape))
    return c[crop].astype(np.result_type(a.dtype, b.dtype, np.float32))


def uniform_filter(input, size, mode="nearest"):
    """Separable rectangular mean; used only by the spoke-analysis tool."""
    if mode != "nearest":
        raise ValueError("only nearest is supported")
    out = np.asarray(input, dtype=np.float64)
    for axis, width in enumerate(_sizes(size, out.ndim)):
        width = int(width)
        if width <= 1:
            continue
        pads = [(0, 0)] * out.ndim
        pads[axis] = (width // 2, (width - 1) // 2)
        a = np.pad(out, pads, mode="edge")
        out = np.apply_along_axis(lambda row: np.convolve(row, np.ones(width) / width, "valid"), axis, a)
    return out


def _jacobian(fun, x):
    # The application's one numerical-Jacobian call used two-point differences.
    h = np.sqrt(np.finfo(float).eps) * np.where(x >= 0, 1.0, -1.0) * np.maximum(1, np.abs(x))
    f = fun(x)
    return np.column_stack([(fun(x + np.eye(len(x))[i] * h[i]) - f) / h[i] for i in range(len(x))])


def solution_certificate(fun, x, jac=None):
    """Diagnostics, not a theorem of convergence or of a unique global minimum."""
    x = np.asarray(x, dtype=float)
    f = np.asarray(fun(x), dtype=float)
    J = np.asarray(jac(x) if callable(jac) else _jacobian(fun, x))
    scales = np.linalg.norm(J, axis=0)
    A = J / np.where(scales > 0, scales, 1)
    singular = np.linalg.svd(A, compute_uv=False)
    rank = int(np.linalg.matrix_rank(A))
    # Normalize before inversion: forming J.T@J in physical units squares an
    # avoidable condition number and can erase a legitimate covariance axis.
    cov = np.linalg.pinv(A.T @ A) / np.outer(np.where(scales > 0, scales, 1), np.where(scales > 0, scales, 1))
    cov *= max(1.0, float(f @ f) / max(1, len(f) - len(x)))
    step = np.linalg.lstsq(A, -f, rcond=None)[0]
    # A separately evaluated derivative catches a small normal residual caused
    # merely by a biased supplied difference formula. Complex step is valid for
    # the analytic polynomial model. Interpolation/absolute-value objectives
    # require finite differences and do not get an analytic certificate.
    try:
        columns = []
        with warnings.catch_warnings():
            warnings.simplefilter('error', np.exceptions.ComplexWarning)
            for i in range(len(x)):
                z = x.astype(complex)
                z[i] += 1e-20j
                value = np.asarray(fun(z))
                if not np.iscomplexobj(value):
                    raise TypeError('objective discards complex perturbations')
                columns.append(value.imag / 1e-20)
        independent = np.column_stack(columns)
        derivative_method = 'complex step (analytic objective required)'
    except (TypeError, ValueError, np.exceptions.ComplexWarning):
        h = np.cbrt(np.finfo(float).eps) * np.maximum(1, np.abs(x))
        independent = np.column_stack([(np.asarray(fun(x + e * hi)) - np.asarray(fun(x - e * hi))) / (2 * hi)
                                       for e, hi in zip(np.eye(len(x)), h)])
        derivative_method = 'central difference diagnostic; derivative error is not rigorously enclosed'
    independent_scales = np.linalg.norm(independent, axis=0)
    independent_A = independent / np.where(independent_scales > 0, independent_scales, 1)
    independent_step = np.linalg.lstsq(independent_A, -f, rcond=None)[0]
    independent_correction = float(np.linalg.norm(independent_A @ independent_step))
    return dict(gradient_inf=float(np.max(np.abs(J.T @ f))),
                normal_residual=float(np.max(np.abs(A.T @ f))),
                correction_sigma=float(np.linalg.norm(A @ step)), cost=float(f @ f / 2),
                rank=rank, parameters=len(x), condition=float(singular[0] / singular[-1]) if singular[-1] else math.inf,
                covariance=cov, stationary=bool(np.linalg.norm(A @ step) < 1e-3 and independent_correction < 1e-3),
                independent_gradient_inf=float(np.max(np.abs(independent.T @ f))),
                independent_normal_residual=float(np.max(np.abs(independent_A.T @ f))),
                independent_correction_sigma=independent_correction, derivative_method=derivative_method,
                global_uniqueness='unproved; rank is only a local test',
                identifiable=bool(rank == len(x) and singular[-1] > singular[0] * 1e-8))


def least_squares(fun, x0, jac="2-point", x_scale=None, method="trf",
                  ftol=1e-8, xtol=1e-8, gtol=1e-8, max_nfev=None):
    """Unbounded linear-loss least squares, solved by an SVD trust region.

    The lm request describes the old call site; this implementation uses the
    same objective with an SVD trust region, not MINPACK's iteration path.
    """
    if method not in ("trf", "lm") or (not callable(jac) and jac != "2-point"):
        raise ValueError("unsupported least-squares configuration")
    x = np.asarray(x0, dtype=float).copy()
    evaluate = lambda z: np.asarray(fun(z), dtype=float)
    derivative = jac if callable(jac) else lambda z: _jacobian(evaluate, z)
    f = evaluate(x)
    J = derivative(x)
    if not np.isfinite(f).all() or not np.isfinite(J).all():
        raise ValueError("non-finite initial residual or Jacobian")
    dynamic = isinstance(x_scale, str) and x_scale == "jac"
    # SciPy 1.18 defaults to jac for lm and 1 for trf.
    dynamic = dynamic or (x_scale is None and method == "lm")
    inverse = np.linalg.norm(J, axis=0) if dynamic else 1 / np.broadcast_to(1.0 if x_scale is None else x_scale, x.shape)
    inverse = np.where(inverse > 0, inverse, 1.0)
    scale = 1 / inverse
    radius = np.linalg.norm(x * inverse) or 1.0
    cost = float(f @ f / 2)
    nfev, status, alpha = 1, 0, 0.0
    limit = max_nfev or 100 * len(x)
    while nfev < limit:
        g = J.T @ f
        if np.linalg.norm(g, ord=np.inf) < gtol:
            status = 1
            break
        A = J * scale
        U, s, VT = np.linalg.svd(A, full_matrices=False)
        uf = U.T @ f
        actual = -1
        while actual <= 0 and nfev < limit:
            step_h, alpha = _trust_step(len(x), len(f), uf, s, VT.T, radius, alpha)
            predicted = -(0.5 * np.sum((A @ step_h) ** 2) + (g * scale) @ step_h)
            step = scale * step_h
            trial = evaluate(x + step)
            nfev += 1
            sn = np.linalg.norm(step_h)
            if not np.isfinite(trial).all():
                radius = max(np.finfo(float).tiny, sn * 0.25)
                continue
            new_cost = float(trial @ trial / 2)
            actual = cost - new_cost
            ratio = actual / predicted if predicted > 0 else float(actual == predicted == 0)
            next_radius = sn * 0.25 if ratio < 0.25 else radius * 2 if ratio > 0.75 and sn > 0.95 * radius else radius
            fs = actual < ftol * cost and ratio > 0.25
            xs = np.linalg.norm(step) < xtol * (xtol + np.linalg.norm(x))
            if fs or xs:
                status = 4 if fs and xs else 2 if fs else 3
                break
            next_radius = max(next_radius, np.finfo(float).tiny)
            alpha *= radius / next_radius
            radius = next_radius
        if actual > 0:
            x += step
            f, cost = trial, new_cost
            J = derivative(x)
            if dynamic:
                inverse = np.maximum(inverse, np.linalg.norm(J, axis=0))
                scale = 1 / inverse
        if status:
            break
    certificate = solution_certificate(fun, x, derivative)
    if not certificate["identifiable"]:
        warnings.warn("fit has flat or unidentifiable parameter directions; uniqueness is unproved", RuntimeWarning, stacklevel=2)
    if not certificate["stationary"]:
        warnings.warn("fit stopped without a first-order certificate; inspect fit uncertainty", RuntimeWarning, stacklevel=2)
    return SimpleNamespace(x=x, fun=f, jac=J, cost=cost, grad=J.T @ f,
                           optimality=float(np.max(np.abs(J.T @ f))), success=status > 0,
                           status=status, message="stopping tolerance reached" if status else "evaluation limit reached",
                           nfev=nfev, certificate=certificate)


def _trust_step(n, m, uf, s, V, radius, alpha):
    """More's SVD trust-region step (SciPy BSD-derived; see NOTICE_NUMERICS)."""
    def phi(a):
        denom = s * s + a
        norm = np.linalg.norm(suf / denom)
        return norm - radius, -np.sum(suf ** 2 / denom ** 3) / norm
    suf = s * uf
    full = m >= n and s[-1] > np.finfo(float).eps * m * s[0]
    if full:
        p = -V @ (uf / s)
        if np.linalg.norm(p) <= radius:
            return p, 0.0
    upper = np.linalg.norm(suf) / radius
    if upper == 0:
        return np.zeros(n), 0.0
    lower = 0.0
    if full:
        value, slope = phi(0.0)
        lower = -value / slope
    if not full and alpha == 0:
        alpha = max(0.001 * upper, math.sqrt(lower * upper))
    for _ in range(10):
        if alpha < lower or alpha > upper:
            alpha = max(0.001 * upper, math.sqrt(lower * upper))
        value, slope = phi(alpha)
        if value < 0:
            upper = alpha
        ratio = value / slope
        lower = max(lower, alpha - ratio)
        alpha -= (value + radius) * ratio / radius
        if abs(value) < 0.01 * radius:
            break
    p = -V @ (suf / (s * s + alpha))
    return p * (radius / np.linalg.norm(p)), alpha


def minimize(fun, x0, method="Nelder-Mead", options=None):
    """The non-adaptive, unbounded Nelder-Mead simplex used by tilephoto."""
    if method != "Nelder-Mead":
        raise ValueError("only Nelder-Mead is supported")
    options = options or {}
    if set(options) - {"maxiter", "xatol", "fatol"}:
        raise ValueError("unsupported Nelder-Mead option")
    x = np.asarray(x0, dtype=float).flatten()
    n = len(x)
    sim = np.tile(x, (n + 1, 1))
    for k in range(n):
        sim[k + 1, k] = 1.05 * x[k] if x[k] else 0.00025
    fs = np.array([fun(q) for q in sim])
    nfev = n + 1
    # Preserve both initial sorts, including tie handling, of the reference.
    for _ in range(2):
        order = np.argsort(fs)
        sim, fs = sim[order], fs[order]
    limit = options.get("maxiter", n * 200)
    xtol, ftol = options.get("xatol", 1e-4), options.get("fatol", 1e-4)
    nit = 1
    while nit < limit:
        if np.max(np.abs(sim[1:] - sim[0])) <= xtol and np.max(np.abs(fs[0] - fs[1:])) <= ftol:
            break
        centre = np.add.reduce(sim[:-1], 0) / n
        xr = 2 * centre - sim[-1]
        fr = fun(xr)
        nfev += 1
        shrink = False
        if fr < fs[0]:
            xe = 3 * centre - 2 * sim[-1]
            fe = fun(xe)
            nfev += 1
            sim[-1], fs[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < fs[-2]:
            sim[-1], fs[-1] = xr, fr
        else:
            outside = fr < fs[-1]
            xc = 1.5 * centre - 0.5 * sim[-1] if outside else 0.5 * centre + 0.5 * sim[-1]
            fc = fun(xc)
            nfev += 1
            if (fc <= fr) if outside else (fc < fs[-1]):
                sim[-1], fs[-1] = xc, fc
            else:
                shrink = True
            if shrink:
                for j in range(1, n + 1):
                    sim[j] = sim[0] + 0.5 * (sim[j] - sim[0])
                    fs[j] = fun(sim[j])
                    nfev += 1
        nit += 1
        order = np.argsort(fs)
        sim, fs = sim[order], fs[order]
    if nit >= limit:
        warnings.warn("photo refinement reached iteration limit; pose is not certified", RuntimeWarning, stacklevel=2)
    return SimpleNamespace(x=sim[0], fun=float(fs[0]), nit=nit, nfev=nfev, success=nit < limit,
                           message="simplex tolerance reached" if nit < limit else "iteration limit reached",
                           final_simplex=(sim, fs))


def f_sf(value, dfn, dfd):
    """F survival via a positive, tail-bounded incomplete-beta series.

    Integer degrees of freedom only. Decimal working arithmetic avoids gamma
    cancellation and subtraction in the small tail. The final result is binary64.
    """
    if dfn <= 0 or dfd <= 0 or int(dfn) != dfn or int(dfd) != dfd:
        raise ValueError("positive integer degrees of freedom required")
    if math.isnan(value):
        return math.nan
    if value <= 0:
        return 1.0
    if math.isinf(value):
        return 0.0
    with localcontext() as ctx:
        ctx.prec = 70
        D = Decimal
        a, b = D(int(dfd)) / 2, D(int(dfn)) / 2
        x = D(int(dfd)) / (D(int(dfd)) + D(int(dfn)) * D.from_float(float(value)))
        complement = x > (a + 1) / (a + b + 2)
        if complement:
            x, a, b = 1 - x, b, a
        pi = D("3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628")
        def gamma_half(z):
            k = int(2 * z)
            if k % 2 == 0:
                return D(math.factorial(k // 2 - 1))
            n = (k - 1) // 2
            return D(math.factorial(2 * n)) / (D(4) ** n * D(math.factorial(n))) * pi.sqrt()
        beta = gamma_half(a) * gamma_half(b) / gamma_half(a + b)
        # Powers of integer/half-integer exponents need no transcendental libm.
        power = lambda z, p: z ** (int(2 * p) // 2) * (z.sqrt() if int(2 * p) % 2 else 1)
        factor = power(x, a) * power(1 - x, b) / (a * beta)
        term = total = D(1)
        for n in range(200000):
            ratio = x * (a + b + n) / (a + 1 + n)
            term *= ratio
            total += term
            future = max(x, x * (a + b + n + 1) / (a + n + 2))
            if future < 1 and factor * term * future / (1 - future) < D("1e-55"):
                result = factor * total
                return float(1 - result if complement else result)
        raise ArithmeticError("incomplete beta series did not reach its tail bound")
