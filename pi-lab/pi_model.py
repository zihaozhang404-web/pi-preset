"""Reference implementation of π's control mathematics.

This is deliberately a second, independent implementation of the same equations
the preset's `control.js` carries, written in Python so the two can be compared
line by line. It exists to answer one question honestly: do the numbers the
agent can compute match a separate implementation of the stated model?

Model (identical to control.js):
    e(t+1) = a*e(t) - b*u(t) + w(t)
    u(t)   = clip(k(t)*e(t) + eps*sigma(t), -umax, umax)
    k(t+1) = clip(k(t) + mu*e(t)*e(t+1), kmin, kmax)      [adaptive arms]
    rho(t) = |a - b*k(t)|
"""

from __future__ import annotations

import math

PI_DIGITS = (
    "3141592653589793238462643383279502884197169399375105820974944592307816406286208"
    "9986280348253421170679"
)
PI_SCALE = 10**100
PI_INT = int(PI_DIGITS)
PI_HALF = PI_SCALE // 2


def pi_frac_int(n: int) -> int:
    """Numerator of frac(n*pi) over PI_SCALE, exact for n <= 1e40."""
    if n < 0:
        raise ValueError("n must be non-negative")
    return (n * PI_INT) % PI_SCALE


def pi_frac(n: int) -> float:
    return pi_frac_int(n) / PI_SCALE


def pi_sign(n: int) -> int:
    return 1 if pi_frac_int(n) < PI_HALF else -1


def mulberry32(seed: int):
    """Bit-exact port of control.js's mulberry32 (uint32 arithmetic)."""
    state = seed & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        # JS: t = (t + imul(t ^ (t >>> 7), 61 | t)) ^ t  — the XOR uses the
        # pre-assignment t, which is why the previous value is kept.
        summed = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t = (summed ^ t) & 0xFFFFFFFF
        t = (t ^ (t >> 14)) & 0xFFFFFFFF
        return t / 4294967296.0

    return nxt


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def disturbance(kind: str, magnitude: float, t: int, period: float, at: int, rng) -> float:
    if kind == "uniform":
        return magnitude * (2 * rng() - 1)
    if kind == "sine":
        return magnitude * math.sin((2 * math.pi * t) / period)
    if kind == "impulse":
        return magnitude if t == at else 0.0
    if kind == "none":
        return 0.0
    raise ValueError(f"unknown disturbance kind: {kind}")


def simulate(
    policy: str,
    horizon: int = 200,
    a: float = 0.9,
    b: float = 1.0,
    k0: float = 0.6,
    mu: float = 0.02,
    kmin: float = 0.0,
    kmax: float = 2.0,
    umax: float = 10.0,
    eps: float = 0.02,
    e0: float = 1.0,
    seed: int = 12345,
    rho_max: float = 0.98,
    settle_tol: float = 0.02,
    disturbance_kind: str = "none",
    disturbance_magnitude: float = 0.1,
    disturbance_period: float = 25.0,
    disturbance_at: int = 20,
    sigma_source=None,
) -> dict:
    """Run one policy arm. Mirrors control.js step order exactly.

    `sigma_source` is a lab-only extension: pass policy="adaptive_custom" with a
    callable t -> +1/-1 to evaluate an alternative deterministic excitation
    without changing the shipped module's behaviour.
    """
    if policy not in {"fixed", "adaptive", "adaptive_random", "adaptive_pi", "adaptive_custom"}:
        raise ValueError(f"unknown policy: {policy}")
    if policy == "adaptive_custom" and sigma_source is None:
        raise ValueError("adaptive_custom requires sigma_source")
    if kmin > kmax:
        raise ValueError("kmin must not exceed kmax")

    rng = mulberry32(seed)
    k = clamp(k0, kmin, kmax)
    e = e0

    errors: list[float] = []
    gains: list[float] = []
    controls: list[float] = []
    saturation = 0
    rho_lo = math.inf
    rho_hi = -math.inf
    stable_steps = 0
    exploration_steps = 0
    finite = True

    for t in range(1, horizon + 1):
        sigma = 0
        explore = 0.0
        if policy == "adaptive_pi":
            sigma = pi_sign(t)
            explore = eps * sigma
            exploration_steps += 1
        elif policy == "adaptive_custom":
            sigma = int(sigma_source(t))
            explore = eps * sigma
            exploration_steps += 1
        elif policy == "adaptive_random":
            sigma = 1 if rng() < 0.5 else -1
            explore = eps * sigma
            exploration_steps += 1

        w = disturbance(
            disturbance_kind, disturbance_magnitude, t, disturbance_period, disturbance_at, rng
        )
        raw_u = k * e + explore
        u = clamp(raw_u, -umax, umax)
        if abs(raw_u - u) > 1e-12:
            saturation += 1

        nxt = a * e - b * u + w
        if not math.isfinite(nxt):
            finite = False

        rho = abs(a - b * k)
        rho_lo = min(rho_lo, rho)
        rho_hi = max(rho_hi, rho)
        if rho <= rho_max:
            stable_steps += 1

        errors.append(nxt)
        gains.append(k)
        controls.append(u)

        if policy != "fixed":
            k = clamp(k + mu * e * nxt, kmin, kmax)
        e = nxt
        if not finite:
            break

    abs_errors = [abs(value) for value in errors]
    rmse = math.sqrt(sum(value * value for value in errors) / max(1, len(errors)))
    mae = sum(abs_errors) / max(1, len(abs_errors))

    settle_step = None
    for index in range(len(abs_errors)):
        if all(value <= settle_tol for value in abs_errors[index:]):
            settle_step = index + 1
            break

    return {
        "policy": policy,
        "steps": len(errors),
        "finite": finite,
        "errors": errors,
        "gains": gains,
        "controls": controls,
        "metrics": {
            "rmse": rmse,
            "mae": mae,
            "maxAbsError": max(abs_errors) if abs_errors else math.nan,
            "finalAbsError": abs_errors[-1] if abs_errors else math.nan,
            "settleStep": settle_step,
            "controlEffort": sum(abs(value) for value in controls),
            "saturationCount": saturation,
            "explorationSteps": exploration_steps,
            "rhoMin": rho_lo,
            "rhoMax": rho_hi,
            "stableFraction": stable_steps / max(1, len(errors)),
            "finalGain": gains[-1] if gains else math.nan,
        },
    }


def gain_interval(a: float, b: float, rho: float) -> tuple[float, float] | None:
    """Analytic set {k : |a - b*k| <= rho}, or None when empty."""
    if b == 0:
        raise ValueError("b must be non-zero")
    low = (a - rho) / b
    high = (a + rho) / b
    lo, hi = min(low, high), max(low, high)
    return (lo, hi) if lo <= hi else None
