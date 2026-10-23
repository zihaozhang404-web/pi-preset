"""Cross-check the shipped JS module against the Python reference.

Reads the JSON emitted by emit_js.mjs (real output of pi-preset/control.js) and
compares every number with an independent Python evaluation of the same
equations. Any disagreement beyond tolerance is reported as a failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pi_model

TOL = 1e-9


def close(left: float, right: float, tol: float = TOL) -> bool:
    if left == right:
        return True
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= tol * scale


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "js-emit.json")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))

    failures: list[str] = []
    checks = 0

    for case in payload["cases"]:
        name = case["name"]
        args = case["args"]
        result = case["result"]

        if name.startswith("simulate:"):
            policy = name.split(":", 1)[1]
            reference = pi_model.simulate(
                policy=policy,
                horizon=args["horizon"],
                a=args["a"],
                b=args["b"],
                k0=args["k0"],
                mu=args["mu"],
                eps=args["eps"],
                seed=args["seed"],
                settle_tol=args["settleTol"],
                disturbance_kind=args["disturbance"],
                disturbance_magnitude=args["disturbanceMagnitude"],
            )
            if result["steps"] != reference["steps"]:
                failures.append(f"{name}: steps {result['steps']} != {reference['steps']}")
                continue
            for key, value in reference["metrics"].items():
                observed = result["metrics"][key]
                checks += 1
                if value is None or observed is None:
                    if value != observed:
                        failures.append(f"{name}: metric {key} {observed} != {value}")
                    continue
                if not close(float(observed), float(value), 1e-6):
                    # control.js rounds reported metrics to 6 decimals; compare
                    # against that declared precision, not raw float equality.
                    failures.append(f"{name}: metric {key} {observed} != {value}")
            # Compare whole series through the sampled points the JS returns.
            for point in result["series"]:
                index = point["t"] - 1
                checks += 1
                if not close(point["e"], reference["errors"][index], 1e-6):
                    failures.append(f"{name}: e[{index}] {point['e']} != {reference['errors'][index]}")
                if not close(point["k"], reference["gains"][index], 1e-6):
                    failures.append(f"{name}: k[{index}] {point['k']} != {reference['gains'][index]}")
                if not close(point["u"], reference["controls"][index], 1e-6):
                    failures.append(f"{name}: u[{index}] {point['u']} != {reference['controls'][index]}")

        elif name == "step:stable":
            e, a, b, k, eps, sigma, w = 1.0, args["a"], args["b"], args["k"], args["eps"], args["sigma"], args["w"]
            u = k * e + eps * sigma
            nxt = a * e - b * u + w
            checks += 2
            if not close(result["outputs"]["u"], u):
                failures.append(f"{name}: u {result['outputs']['u']} != {u}")
            if not close(result["outputs"]["eNext"], nxt, 1e-6):
                failures.append(f"{name}: eNext {result['outputs']['eNext']} != {nxt}")

        elif name.startswith("signal:"):
            for point in result["points"]:
                checks += 1
                expected = pi_model.pi_sign(point["n"])
                if point["sigma"] != expected:
                    failures.append(f"{name}: sigma({point['n']}) {point['sigma']} != {expected}")
                if not close(float(point["r"]), pi_model.pi_frac(point["n"]), 1e-15):
                    failures.append(f"{name}: frac({point['n']}) mismatch")

        elif name == "gain":
            interval = pi_model.gain_interval(args["a"], args["b"], args["rhoTarget"])
            checks += 1
            if interval is None:
                if result["feasibleInterval"] is not None:
                    failures.append(f"{name}: expected no interval")
            else:
                lo, hi = interval
                observed = result["feasibleInterval"]
                if observed is None or not close(observed["kMin"], lo) or not close(observed["kMax"], hi):
                    failures.append(f"{name}: {observed} != [{lo}, {hi}]")

    print(f"checks: {checks}")
    print(f"mismatches: {len(failures)}")
    for line in failures[:20]:
        print("  -", line)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
