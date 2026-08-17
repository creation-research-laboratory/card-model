"""
Root finding, without scipy.

`brentq` here is a line-by-line port of the algorithm in scipy's
``Zeros/brentq.c`` — the same Brent's method, the same convergence test, the
same iteration order.  ``tests/test_solvers.py`` checks it against scipy
directly rather than taking that on trust.

It returns *bit-identical* results for smooth objectives, and that is what the
test asserts there.  It is not identical in every case, and cannot be: the C
compiler is free to contract ``a*b + c`` in the interpolation step into a
fused multiply-add (clang does so by default on arm64), which rounds once
where Python rounds twice.  Where that changes an iterate it moves it by an
ULP or two, and the returned roots then differ by far less than the caller's
own `xtol` — 7e-13 against a requested 1e-10 in the one case this package has
found, an inverse-age solve whose objective is quantized near the root.  The
guarantee to rely on is the one brentq actually makes: a root bracketed to
within `xtol`.

WHY THIS EXISTS.  `models.py` and `calibrate.py` need exactly one thing from
scipy: a bracketed 1-D root solve.  Importing scipy to get it costs 13.4 MB in
a Pyodide build and pulls numpy (2.8 MB) along with it, against a 5.8 MB
Python runtime — the two wheels are nearly three times the size of the
interpreter.  A 60-line function removes both, and lets the numerical core run
anywhere CPython does: a browser, a lambda, a minimal container.

This is deliberately NOT a general-purpose optimization module.  It is the one
routine the model path needs.  Anything requiring real scipy — the `quad`
fallback in `DecayModel.compute_integral`, everything in `inference.py` —
should keep importing scipy, lazily, where it is used.
"""

__all__ = ["brentq"]

#: scipy's default relative tolerance, and its minimum permitted value:
#: 4 * numpy.finfo(float).eps.  A tighter rtol cannot be honored in float64,
#: so scipy rejects it rather than looping to maxiter; we match that.
_RTOL_MIN = 4.0 * 2.220446049250313e-16


def brentq(f, a, b, xtol=2e-12, rtol=_RTOL_MIN, maxiter=100, args=()):
    """
    Find a root of `f` in [a, b] by Brent's method.

    Brent's method combines bisection with inverse quadratic interpolation:
    it keeps the root bracketed at every step (so it cannot diverge the way a
    Newton or secant iteration can) while converging superlinearly on smooth
    functions.  That combination is why the package uses bracketed solves
    throughout and why `calibrate.py` refuses to go back to an initial-guess
    solver.

    Signature and semantics match `scipy.optimize.brentq` for the arguments
    this package uses.  `full_output` and `disp` are not implemented, because
    nothing here needs them.

    Args:
        f: Continuous function of one variable.  `f(a)` and `f(b)` must have
            opposite signs (or one of them must be exactly zero).
        a: Lower end of the bracketing interval.
        b: Upper end of the bracketing interval.
        xtol: Absolute tolerance on the root.  Must be positive.
        rtol: Relative tolerance on the root.  Must be at least
            4 * float epsilon, which is also the default.
        maxiter: Maximum iterations before giving up.
        args: Extra positional arguments passed through to `f`.

    Returns:
        A value x in [a, b] with f(x) approximately 0.

    Raises:
        ValueError: If the tolerances are out of range, or if `f(a)` and
            `f(b)` have the same sign so no root is bracketed.
        RuntimeError: If `maxiter` iterations pass without converging.
    """
    if xtol <= 0:
        raise ValueError(f"xtol must be positive, got {xtol!r}")
    if rtol < _RTOL_MIN:
        raise ValueError(
            f"rtol must be at least {_RTOL_MIN!r} (4 * float epsilon), got "
            f"{rtol!r}.  A tighter relative tolerance is not representable in "
            "float64."
        )

    xpre, xcur = float(a), float(b)
    fpre = f(xpre, *args)
    fcur = f(xcur, *args)

    # An exact hit at either end is a root; check before the sign test, since
    # a zero endpoint makes the product zero rather than negative.
    if fpre == 0.0:
        return xpre
    if fcur == 0.0:
        return xcur
    if fpre * fcur > 0.0:
        raise ValueError(
            f"f(a) and f(b) must have different signs: f({xpre!r}) = {fpre!r} "
            f"and f({xcur!r}) = {fcur!r} do not bracket a root."
        )

    xblk = fblk = spre = scur = 0.0

    for _ in range(maxiter):
        # Keep (xcur, xblk) straddling the root, with xcur the better estimate.
        if fpre * fcur < 0.0:
            xblk, fblk = xpre, fpre
            spre = scur = xcur - xpre
        if abs(fblk) < abs(fcur):
            xpre, xcur, xblk = xcur, xblk, xcur
            fpre, fcur, fblk = fcur, fblk, fcur

        delta = (xtol + rtol * abs(xcur)) / 2.0
        sbis = (xblk - xcur) / 2.0

        if fcur == 0.0 or abs(sbis) < delta:
            return xcur

        if abs(spre) > delta and abs(fcur) < abs(fpre):
            if xpre == xblk:
                # Only two distinct points: secant step.
                stry = -fcur * (xcur - xpre) / (fcur - fpre)
            else:
                # Three distinct points: inverse quadratic interpolation.
                dpre = (fpre - fcur) / (xpre - xcur)
                dblk = (fblk - fcur) / (xblk - xcur)
                stry = (-fcur * (fblk * dblk - fpre * dpre)
                        / (dblk * dpre * (fblk - fpre)))
            if 2.0 * abs(stry) < min(abs(spre), 3.0 * abs(sbis) - delta):
                # The interpolated step is short enough to trust.
                spre, scur = scur, stry
            else:
                # It is not, so fall back to bisection.  This guard is what
                # keeps the worst case bounded instead of letting a bad
                # interpolation stall the iteration.
                spre = scur = sbis
        else:
            spre = scur = sbis

        xpre, fpre = xcur, fcur
        if abs(scur) > delta:
            xcur += scur
        else:
            xcur += delta if sbis > 0.0 else -delta
        fcur = f(xcur, *args)

    raise RuntimeError(
        f"brentq failed to converge in {maxiter} iterations; the last "
        f"estimate was {xcur!r}."
    )
