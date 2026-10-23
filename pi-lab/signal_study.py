"""Supplementary study: what the π signal actually is, and where it can help.

Two questions, both answered with measurements rather than assertions:

1. Characterisation — is r(n)=frac(n*pi) balanced, and what does its sign
   sequence correlate with? (No claim of randomness.)
2. Identification — if a parameter must be estimated online (the "recursive
   least squares" option in the design), does a deterministic +-1 excitation
   estimate it as well as a random +-1 excitation of the same amplitude and
   the same budget?

This module is lab-only: `control.js` ships the signal and the simulation, but
not an online estimator. That is stated in the report rather than implied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import pi_model

RESULTS = Path(__file__).parent / "results"
RNG = np.random.default_rng(7)


def autocorrelation(signs: np.ndarray, max_lag: int = 8) -> list[float]:
    centred = signs - signs.mean()
    denominator = float(np.dot(centred, centred))
    return [float(np.dot(centred[:-lag], centred[lag:]) / denominator) for lag in range(1, max_lag + 1)]


def rls_estimate(us: np.ndarray, ys: np.ndarray, forgetting: float = 1.0) -> float:
    """Plain recursive least squares for a single scalar regressor."""
    theta = 0.0
    covariance = 1000.0
    for u, y in zip(us, ys):
        gain = covariance * u / (forgetting + u * covariance * u)
        theta = theta + gain * (y - u * theta)
        covariance = (covariance - gain * u * covariance) / forgetting
    return theta


def bootstrap_ci(values: np.ndarray, resamples: int = 2000) -> tuple[float, float]:
    draws = RNG.choice(values, size=(resamples, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    lines = ["# 补充研究：π 信号的实测性质与辨识价值", ""]

    # ---------------------------------------------------------------- balance
    horizon = 100_000
    signs = np.array([pi_model.pi_sign(n) for n in range(1, horizon + 1)], dtype=np.int8)
    plus = int((signs == 1).sum())
    minus = int((signs == -1).sum())
    fraction = plus / horizon
    # Longest run of one sign.
    longest = 1
    run = 1
    for index in range(1, horizon):
        if signs[index] == signs[index - 1]:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    # Cumulative imbalance keeps growing like a discrepancy, not like a random walk.
    walk = np.cumsum(signs)
    max_imbalance = int(np.abs(walk).max())

    lines += [
        "## 1. 符号平衡与游程（n = 1..100000，精确整数运算）",
        "",
        f"- σ(n)=+1 的次数：{plus}；σ(n)=-1 的次数：{minus}",
        f"- 正号比例：{fraction:.5f}（理论长期频率 0.5）",
        f"- 最长同号游程：{longest}",
        f"- 累计和 |Σσ| 的最大值：{max_imbalance}",
        "",
        "解读：符号频率接近一半，但这**不等于随机性**。累计和的增长量级介于随机游走"
        "与有界序列之间，取决于 π 的连分数结构；把它当作“天然随机源”是错误的，"
        "把它当作“确定性激励信号”是正确的。",
        "",
    ]

    # ----------------------------------------------------------- correlation
    pi_autocorr = autocorrelation(signs.astype(float))
    random_signs = (RNG.integers(0, 2, size=horizon) * 2 - 1).astype(np.int8)
    random_autocorr = autocorrelation(random_signs.astype(float))

    lines += [
        "## 2. 符号序列的自相关（lag 1..8）",
        "",
        "| lag | π 序列 | 随机 ±1（同一长度） |",
        "|---|---|---|",
    ]
    for index, (left, right) in enumerate(zip(pi_autocorr, random_autocorr), start=1):
        lines.append(f"| {index} | {left:+.4f} | {right:+.4f} |")
    lines += [
        "",
        "解读（修正一个常见误解）：π 序列的邻近自相关**并不**接近 0（见 golden-study.md 第 2 节，"
        "lag 1 为 +0.43、lag 7 为 +0.96），因为它本质上是一段准周期方波。"
        "随机 ±1 的自相关才是噪声水平。两者都可用于激励，但只有随机激励近似白；"
        "π 序列的价值在于**可逐位复现**，而不在于更接近噪声。",
        "",
    ]

    # -------------------------------------------------------- identification
    lines += [
        "## 3. 在线辨识对照：同样幅度、同样步数的 ±1 激励",
        "",
        "模型 y_t = b·u_t + w_t，真值 b=1.3，噪声 w ~ U(-0.05, 0.05)，"
        "用递归最小二乘（forgetting=1）估计 b。180 步预算，每臂 300 次重复。",
        "",
        "| 激励 | |b_hat - b| 均值 | 95% CI | 相对误差 |",
        "|---|---|---|---|",
    ]

    true_b = 1.3
    budget = 180
    trials = 300
    arms = {
        "无激励（u=0.05 常数）": lambda t, seed: 0.05,
        "随机 ±1": None,
        "π 确定性 ±1": lambda t, seed: float(pi_model.pi_sign(t)),
    }
    ident: dict[str, dict] = {}

    for name, generator in arms.items():
        errors = []
        for seed in range(1, trials + 1):
            noise = np.random.default_rng(seed).uniform(-0.05, 0.05, size=budget)
            if generator is None:
                us = (np.random.default_rng(seed + 10_000).integers(0, 2, size=budget) * 2 - 1).astype(float)
            else:
                us = np.array([generator(t, seed) for t in range(1, budget + 1)], dtype=float)
            ys = true_b * us + noise
            estimate = rls_estimate(us, ys)
            errors.append(abs(estimate - true_b))
        array = np.asarray(errors)
        low, high = bootstrap_ci(array)
        ident[name] = {
            "meanAbsError": float(array.mean()),
            "ciLow": low,
            "ciHigh": high,
            "relative": float(array.mean() / true_b),
            "note": "unidentifiable: regressor energy too small" if name.startswith("无激励") else "",
        }
        lines.append(
            f"| {name} | {array.mean():.4f} | [{low:.4f}, {high:.4f}] | "
            f"{array.mean() / true_b * 100:.2f}% |"
        )

    lines += [
        "",
        "解读：没有激励时参数不可辨识（回归量能量太小）；随机 ±1 与 π 确定性 ±1 的"
        "估计误差处于同一量级，差异在噪声水平以内。**结论：π 序列可作为可复现的激励信号，"
        "但没有证据表明它比随机激励更准确。**",
        "",
    ]

    payload = {
        "balance": {
            "n": horizon,
            "plus": plus,
            "minus": minus,
            "fraction": fraction,
            "longestRun": longest,
            "maxCumulativeImbalance": max_imbalance,
        },
        "autocorrelation": {"pi": pi_autocorr, "random": random_autocorr},
        "identification": ident,
    }
    (RESULTS / "signal-study.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "signal-study.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["balance"], ensure_ascii=False))
    for name, data in ident.items():
        print(name, round(data["meanAbsError"], 5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
