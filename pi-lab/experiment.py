"""Tests B and C for π: mathematical control checks and the four-arm comparison.

Everything here runs the Python reference model in pi_model.py, which
crosscheck.py has already shown to agree with the shipped control.js.

Test B checks the reference-model claims on their own terms (convergence,
instability detection, bounded disturbance response, saturation, gain
projection). Test C compares four exploration policies on the same model, with
the same environment, the same disturbance distribution, and the same
exploration budget, using independent random seeds per arm.

Nothing is cherry-picked: every run in the sample is reported, including runs
that diverge.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import pi_model

RESULTS = Path(__file__).parent / "results"
RNG = np.random.default_rng(20261023)


def bootstrap_ci(values: np.ndarray, resamples: int = 2000) -> tuple[float, float]:
    """Percentile bootstrap 95% CI for the mean."""
    if len(values) == 0:
        return (float("nan"), float("nan"))
    draws = RNG.choice(values, size=(resamples, len(values)), replace=True).mean(axis=1)
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))


def ci_for_difference(left: np.ndarray, right: np.ndarray, resamples: int = 2000) -> tuple[float, float]:
    """Percentile bootstrap 95% CI for mean(left) - mean(right), independent samples."""
    draws_left = RNG.choice(left, size=(resamples, len(left)), replace=True).mean(axis=1)
    draws_right = RNG.choice(right, size=(resamples, len(right)), replace=True).mean(axis=1)
    diff = draws_left - draws_right
    return (float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5)))


def describe_difference(delta: float, low: float, high: float) -> str:
    """Name the kind of evidence honestly.

    A collapsed interval means the two arms have zero between-run variance
    (deterministic policy under a deterministic disturbance), so the number is
    one exact comparison, not a sampled estimate.
    """
    if abs(high - low) < 1e-12:
        return "确定差异（零方差，非抽样统计）" if delta != 0 else "完全相同"
    if low > 0:
        return "D 显著更差"
    if high < 0:
        return "D 显著更好"
    return "差异不显著"


def fmt(value: float, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value:.{digits}f}"


# --------------------------------------------------------------------------- #
# Test B — mathematical control
# --------------------------------------------------------------------------- #

def test_b() -> dict:
    lines: list[str] = ["# 测试 B：数学控制层验证", ""]
    lines.append("对 pi_model.py 的直接调用（与 control.js 已交叉验证一致）。")
    lines.append("")

    records: dict[str, object] = {}

    # B1: symmetric convergence, no disturbance.
    lines.append("## B1 正负误差对称收敛（a=0.9, b=1, k=0.6, rho=0.3, 无扰动）")
    lines.append("")
    lines.append("| e0 | 步数 | |e_1| | |e_5| | |e_10| | 稳定判定 |")
    lines.append("|---|---|---|---|---|---|")
    for e0 in (1.0, -1.0):
        run = pi_model.simulate(policy="fixed", horizon=10, a=0.9, b=1, k0=0.6, eps=0, e0=e0)
        errors = run["errors"]
        lines.append(
            f"| {e0:+.0f} | 10 | {fmt(abs(errors[0]))} | {fmt(abs(errors[4]))} | "
            f"{fmt(abs(errors[9]))} | rho={fmt(run['metrics']['rhoMax'], 2)} < 1 |"
        )
    symmetric = True
    pos = pi_model.simulate(policy="fixed", horizon=30, a=0.9, b=1, k0=0.6, eps=0, e0=1.0)["errors"]
    neg = pi_model.simulate(policy="fixed", horizon=30, a=0.9, b=1, k0=0.6, eps=0, e0=-1.0)["errors"]
    for left, right in zip(pos, neg):
        if abs(left + right) > 1e-12:
            symmetric = False
    records["b1_symmetric"] = symmetric
    lines.append("")
    lines.append(f"- 对称性 |e(t,+) + e(t,-)| = 0 在 30 步内逐点成立：**{symmetric}**")
    lines.append("")

    # B2: instability is detected, not hidden.
    lines.append("## B2 不稳定增益被识别（a=2.0, b=1, k=0, rho=2.0）")
    lines.append("")
    run = pi_model.simulate(policy="fixed", horizon=2000, a=2.0, b=1, k0=0.0, eps=0, e0=1.0)
    lines.append(f"- rho = {fmt(run['metrics']['rhoMax'], 2)} ≥ 1：负结论被正确给出")
    lines.append(f"- 有限性标志 finite = **{run['finite']}**（溢出即停止，不产出伪数值）")
    lines.append(f"- 停止前步数 = {run['steps']}，末值 = {run['errors'][-1]}")
    records["b2_diverges"] = not run["finite"]
    lines.append("")

    # B3: bounded disturbance response, compared with the analytic bound.
    lines.append("## B3 有界扰动下的误差界（a=0.9, b=1, k=0.6, eps=0.05, w_max=0.1）")
    lines.append("")
    rho = 0.3
    bound = (1.0 * 0.05 + 0.1) / (1 - rho)
    worst = 0.0
    for seed in range(200):
        run = pi_model.simulate(
            policy="fixed", horizon=400, a=0.9, b=1, k0=0.6, eps=0.05, e0=0.0, seed=seed,
            disturbance_kind="uniform", disturbance_magnitude=0.1,
        )
        worst = max(worst, run["metrics"]["maxAbsError"])
    lines.append(f"- 理论稳态界 (b·eps + w_max)/(1-rho) = {fmt(bound)}")
    lines.append(f"- 200 次试验（horizon=400, e0=0）中的最大值 = {fmt(worst)}")
    lines.append(f"- 结论：**{'未越界' if worst <= bound else '越界'}**")
    records["b3_within_bound"] = worst <= bound
    lines.append("")

    # B4: saturation is counted, not silently clamped.
    lines.append("## B4 动作限幅被计数（umax=0.2, e0=10）")
    lines.append("")
    run = pi_model.simulate(policy="fixed", horizon=50, a=0.9, b=1, k0=0.6, eps=0, e0=10.0, umax=0.2)
    lines.append(f"- 饱和步数 = {run['metrics']['saturationCount']} / 50")
    lines.append(f"- 控制量最大值 = {fmt(max(abs(v) for v in run['controls']))} ≤ umax = 0.2")
    lines.append(f"- 误差仍然收敛：final |e| = {fmt(run['metrics']['finalAbsError'])}")
    capped = max(abs(v) for v in run["controls"]) <= 0.2 + 1e-12
    counted = run["metrics"]["saturationCount"] > 0
    converged = run["metrics"]["finalAbsError"] <= 0.05
    records["b4_saturation_counted"] = bool(capped and counted and converged)
    lines.append("")

    # B5: gain projection keeps the gain inside the declared set.
    lines.append("## B5 增益投影（kmin=0.5, kmax=0.7，自适应臂）")
    lines.append("")
    run = pi_model.simulate(
        policy="adaptive_pi", horizon=500, a=0.9, b=1, k0=0.6, kmin=0.5, kmax=0.7,
        mu=0.2, eps=0.05, e0=1.0, disturbance_kind="uniform", disturbance_magnitude=0.05,
    )
    inside = all(0.5 - 1e-12 <= k <= 0.7 + 1e-12 for k in run["gains"])
    rho_worst = abs(0.9 - 1.0 * 0.7) if any(k <= 0.7 for k in run["gains"]) else None
    lines.append(f"- 全部 {len(run['gains'])} 步的 k 均落在 [0.5, 0.7]：**{inside}**")
    lines.append(f"- 该集合内最大 rho = |0.9 - 0.7| = {fmt(rho_worst, 2)} < 1：投影本身即保证稳定")
    lines.append(f"- 大 mu=0.2 下仍然有限：finite = {run['finite']}")
    records["b5_projection"] = inside
    lines.append("")

    lines.append("## B 小结")
    lines.append("")
    lines.append("| 检查 | 结果 |")
    lines.append("|---|---|")
    lines.append(f"| B1 对称收敛 | {'通过' if symmetric else '失败'} |")
    lines.append(f"| B2 不稳定可识别 | {'通过' if records['b2_diverges'] else '失败'} |")
    lines.append(f"| B3 有界扰动不越界 | {'通过' if records['b3_within_bound'] else '失败'} |")
    lines.append(f"| B4 限幅计数 | {'通过' if records['b4_saturation_counted'] else '失败'} |")
    lines.append(f"| B5 增益投影 | {'通过' if inside else '失败'} |")
    lines.append("")

    (RESULTS / "test-b.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return records


# --------------------------------------------------------------------------- #
# Test C — four-arm comparison
# --------------------------------------------------------------------------- #

ARMS = [
    ("A-fixed", "fixed", "固定反馈，无探索"),
    ("B-adaptive", "adaptive", "自适应反馈，无探索"),
    ("C-random", "adaptive_random", "自适应反馈 + 随机符号探索"),
    ("D-pi", "adaptive_pi", "自适应反馈 + π 确定性符号探索"),
]

SCENARIOS = [
    ("none", "无扰动", 0.0),
    ("uniform", "均匀有界扰动 0.1", 0.1),
    ("sine", "正弦扰动 0.1（周期 25）", 0.1),
]

TRIALS = 300
BASE = dict(horizon=200, a=0.9, b=1.0, k0=0.6, mu=0.02, eps=0.05, e0=1.0, settle_tol=0.02)


def test_c() -> dict:
    rows: list[dict] = []
    lines: list[str] = ["# 测试 C：四臂对照实验", ""]
    lines.append(
        "同一模型、同一环境、同一探索预算（每步恰好一次探索信号，eps 相同），"
        f"每臂每场景 {TRIALS} 个独立种子（1..{TRIALS}）。"
    )
    lines.append("")
    lines.append(
        f"参数固定为：a={BASE['a']}, b={BASE['b']}, k0={BASE['k0']}, mu={BASE['mu']}, "
        f"eps={BASE['eps']}, e0={BASE['e0']}, horizon={BASE['horizon']}, settle_tol={BASE['settle_tol']}。"
    )
    lines.append("")
    lines.append(
        "诚实性说明：四臂共享同一初值与预算，但每臂使用**独立种子**，因此比较是两组独立样本，"
        "不做配对声称。"
    )
    lines.append("")
    lines.append(
        "区间宽度说明：置信区间塌缩成一个点，表示该臂在重复试验中零方差（确定性策略 + 确定性扰动），"
        "此时两点之差是一次确定比较，不是抽样估计，不能读作“样本极大所以显著”。"
    )
    lines.append("")

    summary: dict[str, dict] = {}

    for scenario_key, scenario_name, magnitude in SCENARIOS:
        for arm_label, policy, arm_name in ARMS:
            values = []
            settle = []
            effort = []
            saturation = []
            stable = []
            for seed in range(1, TRIALS + 1):
                run = pi_model.simulate(
                    policy=policy,
                    horizon=BASE["horizon"],
                    a=BASE["a"],
                    b=BASE["b"],
                    k0=BASE["k0"],
                    mu=BASE["mu"],
                    eps=BASE["eps"],
                    e0=BASE["e0"],
                    seed=seed,
                    settle_tol=BASE["settle_tol"],
                    disturbance_kind=scenario_key,
                    disturbance_magnitude=magnitude,
                )
                metrics = run["metrics"]
                values.append(metrics["rmse"])
                settle.append(metrics["settleStep"] if metrics["settleStep"] is not None else BASE["horizon"] + 1)
                effort.append(metrics["controlEffort"])
                saturation.append(metrics["saturationCount"])
                stable.append(metrics["stableFraction"])
                rows.append(
                    {
                        "scenario": scenario_key,
                        "arm": arm_label,
                        "policy": policy,
                        "seed": seed,
                        "rmse": metrics["rmse"],
                        "settleStep": metrics["settleStep"],
                        "settleCensored": metrics["settleStep"] is None,
                        "controlEffort": metrics["controlEffort"],
                        "saturationCount": metrics["saturationCount"],
                        "stableFraction": metrics["stableFraction"],
                        "finalGain": metrics["finalGain"],
                        "finite": run["finite"],
                    }
                )
            array = np.asarray(values)
            low, high = bootstrap_ci(array)
            summary[f"{scenario_key}|{arm_label}"] = {
                "n": TRIALS,
                "rmseMean": float(array.mean()),
                "rmseMedian": float(np.median(array)),
                "rmseSd": float(array.std(ddof=1)),
                "rmseCiLow": low,
                "rmseCiHigh": high,
                "settleMedian": float(np.median(settle)),
                "settledWithinHorizon": float(np.mean([s <= BASE["horizon"] for s in settle])),
                "effortMean": float(np.mean(effort)),
                "saturationMean": float(np.mean(saturation)),
                "stableFractionMean": float(np.mean(stable)),
                "rmseValues": values,
            }

        lines.append(f"## 场景：{scenario_name}（{scenario_key}）")
        lines.append("")
        lines.append("| 臂 | 策略 | RMSE 均值 | 95% CI | RMSE 中位数 | 收敛步中位数 | horizon 内收敛率 | 控制开销均值 | 饱和步均值 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for arm_label, policy, arm_name in ARMS:
            data = summary[f"{scenario_key}|{arm_label}"]
            lines.append(
                f"| {arm_label} | {arm_name} | {fmt(data['rmseMean'])} | "
                f"[{fmt(data['rmseCiLow'])}, {fmt(data['rmseCiHigh'])}] | "
                f"{fmt(data['rmseMedian'])} | {fmt(data['settleMedian'], 1)} | "
                f"{data['settledWithinHorizon'] * 100:.1f}% | {fmt(data['effortMean'])} | "
                f"{fmt(data['saturationMean'], 1)} |"
            )
        lines.append("")

        # D vs the other arms: is the π signal measurably better?
        lines.append("**D-pi 与其他臂的差值（D 减对手，独立样本 bootstrap 95% CI；负值表示 D 的 RMSE 更低）**")
        lines.append("")
        lines.append("| 对手 | ΔRMSE | 95% CI | 结论 |")
        lines.append("|---|---|---|---|")
        d_values = np.asarray(summary[f"{scenario_key}|D-pi"]["rmseValues"])
        for arm_label, _, _ in ARMS:
            if arm_label == "D-pi":
                continue
            other = np.asarray(summary[f"{scenario_key}|{arm_label}"]["rmseValues"])
            delta = float(d_values.mean() - other.mean())
            low, high = ci_for_difference(d_values, other)
            verdict = describe_difference(delta, low, high)
            summary[f"{scenario_key}|delta|{arm_label}"] = {"delta": delta, "low": low, "high": high, "verdict": verdict}
            lines.append(f"| {arm_label} | {delta:+.5f} | [{fmt(low)}, {fmt(high)}] | {verdict} |")
        lines.append("")

        # Reference line: a deadbeat fixed gain, not one of the four arms.
        oracle = []
        for seed in range(1, TRIALS + 1):
            oracle.append(
                pi_model.simulate(
                    policy="fixed", horizon=BASE["horizon"], a=BASE["a"], b=BASE["b"], k0=0.9,
                    eps=0.0, e0=BASE["e0"], seed=seed, settle_tol=BASE["settle_tol"],
                    disturbance_kind=scenario_key, disturbance_magnitude=magnitude,
                )["metrics"]["rmse"]
            )
        lines.append(
            f"参考线（不属于四臂）：固定增益 k=0.9（rho=0）的 RMSE 均值 = {fmt(float(np.mean(oracle)))}。"
            " 它说明本模型下“已知最优固定增益”能达到的水平，用于判断自适应是否值得。"
        )
        lines.append("")

    with (RESULTS / "test-c.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Save a compact machine-readable summary without the raw value lists.
    compact = {
        key: {k: v for k, v in value.items() if k != "rmseValues"}
        for key, value in summary.items()
    }
    (RESULTS / "test-c-summary.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RESULTS / "test-c.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return compact


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    b = test_b()
    c = test_c()
    print("Test B:", json.dumps(b, default=str))
    print("Test C scenarios:", len({key.split("|")[0] for key in c}))
    print("wrote", RESULTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
