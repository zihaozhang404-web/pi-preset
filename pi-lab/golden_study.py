"""Where the π sign sequence is structurally weak, and what fixes it.

The first signal study found a property of r(n)=frac(n*pi) that matters more
than anything else in this design: sigma(n) is *almost periodic*, because
7*pi = 21.9911... is close to an integer, and 113*pi is far closer still. A
near-periodic excitation is not low-discrepancy: its autocorrelation stays high
and, inside a feedback loop, its "exploration" adds a coherent bias instead of
averaging out.

This module measures that property directly, then tests the obvious repair: a
one-line variant using a badly approximable irrational, the golden-ratio
fraction phi = (sqrt(5)-1)/2 ~ 0.6180339887, whose continued fraction is
[0;1,1,1,...] and therefore has the best possible equidistribution. Same
amplitude, same budget, same loop.

Lab-only: `control.js` ships `pi` exploration, not this variant. The comparison
is evidence for a design change, not a shipped feature.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import pi_model

RESULTS = Path(__file__).parent / "results"
RNG = np.random.default_rng(11)

PHI = (math.sqrt(5) - 1) / 2


def phase_sign(n: int, alpha: float) -> int:
    """sigma(n) = +1 when frac(n*alpha) < 1/2, else -1."""
    return 1 if ((n * alpha) % 1.0) < 0.5 else -1


def autocorrelation(signs: np.ndarray, max_lag: int = 8) -> list[float]:
    centred = signs - signs.mean()
    denominator = float(np.dot(centred, centred))
    return [float(np.dot(centred[:-lag], centred[lag:]) / denominator) for lag in range(1, max_lag + 1)]


def agreement(signs: np.ndarray, lag: int) -> float:
    """Fraction of positions where sigma(n+lag) == sigma(n)."""
    return float(np.mean(signs[:-lag] == signs[lag:]))


def bootstrap_ci(values: np.ndarray, resamples: int = 2000) -> tuple[float, float]:
    draws = RNG.choice(values, size=(resamples, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    n_max = 100_000
    pi_signs = np.array([pi_model.pi_sign(n) for n in range(1, n_max + 1)], dtype=np.int8)
    phi_signs = np.array([phase_sign(n, PHI) for n in range(1, n_max + 1)], dtype=np.int8)
    random_signs = (np.random.default_rng(99).integers(0, 2, size=n_max) * 2 - 1).astype(np.int8)

    lines = ["# π 序列的结构缺陷与替代方案（实验室结论）", ""]

    lines += [
        "## 1. 近周期性：σ(n) 与 σ(n+k) 的一致率",
        "",
        "7π ≈ 21.9911、113π ≈ 354.99997，因此 π 序列在 lag 7 与 lag 113 附近几乎复现自身。",
        "",
        "| lag | π 序列一致率 | φ 序列一致率 | 随机 ±1 的一致率 |",
        "|---|---|---|---|",
    ]
    for lag in (1, 2, 3, 7, 22, 113, 355):
        lines.append(
            f"| {lag} | {agreement(pi_signs, lag) * 100:.2f}% | "
            f"{agreement(phi_signs, lag) * 100:.2f}% | {agreement(random_signs, lag) * 100:.2f}% |"
        )
    lines.append("")

    pi_ac = autocorrelation(pi_signs.astype(float))
    phi_ac = autocorrelation(phi_signs.astype(float))
    lines += [
        "## 2. 自相关（lag 1..8，n=100000）",
        "",
        "| lag | π 序列 | φ 序列 |",
        "|---|---|---|",
    ]
    for index, (left, right) in enumerate(zip(pi_ac, phi_ac), start=1):
        lines.append(f"| {index} | {left:+.4f} | {right:+.4f} |")
    lines += [
        "",
        "解读（与直觉相反，但测量结果如此）：π 序列的邻近自相关远不为零——lag 1 为 +0.43，"
        "lag 7 为 +0.96，lag 3/4 为明显的负相关。它是一段**准周期方波**："
        "因为 7π 与 113π 都极接近整数，序列在 lag 7 处有 98% 位相同，在 lag 113 处有 99.99% 位相同。",
        "",
        "φ（黄金比）**也没有**变成白噪声：它的 lag 4 自相关为 -0.89、lag 8 为 +0.78，"
        "lag 1 一致率只有 23.6%（强烈交替）。这说明：**相位 frac(nα) 的低差异性与符号序列的"
        "白噪声性是两个不同的性质**，任何无理旋转的二值化都会留下长程结构。",
        "",
        "因此本节的结论不是“φ 更白”，而是“π 的结构恰好锁在很短的周期 7 上，"
        "φ 把结构分散到更长的尺度”，第 3 节测量这种差别在闭环里的实际代价。",
        "",
    ]

    # -------------------------------------------------- closed-loop comparison
    base = dict(
        horizon=200, a=0.9, b=1.0, k0=0.6, mu=0.02, eps=0.05, e0=1.0, settle_tol=0.02
    )
    trials = 300
    lines += [
        "## 3. 闭环表现：同一模型、同一预算，仅替换探索信号",
        "",
        f"参数：{', '.join(f'{k}={v}' for k, v in base.items())}；每臂 {trials} 次重复；"
        "四臂分别为无探索、随机 ±1、π ±1、φ ±1。",
        "",
    ]

    arms = {
        "无探索（自适应）": ("adaptive", None),
        "随机 ±1": ("adaptive_random", None),
        "π ±1（已发货）": ("adaptive_pi", None),
        "φ ±1（候选）": ("adaptive_custom", lambda t: phase_sign(t, PHI)),
    }
    results: dict[str, dict] = {}

    for scenario, magnitude in (("none", 0.0), ("uniform", 0.1)):
        lines.append(f"### 场景 {scenario}（扰动幅度 {magnitude}）")
        lines.append("")
        lines.append("| 激励 | RMSE 均值 | 95% CI | 收敛率 |")
        lines.append("|---|---|---|---|")
        for label, (policy, sigma_source) in arms.items():
            values = []
            settled = 0
            for seed in range(1, trials + 1):
                run = pi_model.simulate(
                    policy=policy,
                    seed=seed,
                    disturbance_kind=scenario,
                    disturbance_magnitude=magnitude,
                    sigma_source=sigma_source,
                    **base,
                )
                values.append(run["metrics"]["rmse"])
                if run["metrics"]["settleStep"] is not None:
                    settled += 1
            array = np.asarray(values)
            low, high = bootstrap_ci(array)
            results[f"{scenario}|{label}"] = {
                "mean": float(array.mean()),
                "ciLow": low,
                "ciHigh": high,
                "settledRate": settled / trials,
                "values": values,
            }
            lines.append(f"| {label} | {array.mean():.5f} | [{low:.5f}, {high:.5f}] | {settled / trials * 100:.1f}% |")
        lines.append("")

        pi_vals = np.asarray(results[f"{scenario}|π ±1（已发货）"]["values"])
        phi_vals = np.asarray(results[f"{scenario}|φ ±1（候选）"]["values"])
        delta = phi_vals - pi_vals
        draws = RNG.choice(delta, size=(2000, len(delta)), replace=True).mean(axis=1)
        low, high = float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
        results[f"{scenario}|delta"] = {"delta": float(delta.mean()), "low": low, "high": high}
        mean_delta = float(delta.mean())
        verdict = (
            "确定差异（零方差，非抽样统计）"
            if abs(high - low) < 1e-12 and mean_delta != 0
            else ("完全相同" if abs(high - low) < 1e-12 else ("φ 显著更好" if high < 0 else ("π 显著更好" if low > 0 else "差异不显著")))
        )
        lines.append(
            f"φ 减 π 的 RMSE 差值 = {mean_delta:+.5f}，95% CI [{low:+.5f}, {high:+.5f}] → **{verdict}**"
        )
        lines.append("")

    summary = {
        key: ({k: v for k, v in value.items() if k != "values"} if "values" in value else value)
        for key, value in results.items()
    }
    (RESULTS / "golden-study.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "golden-study.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in summary.items():
        print(key, {k: (round(v, 6) if isinstance(v, float) else v) for k, v in value.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
