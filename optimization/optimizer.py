"""Budget-constrained dataset selection.

The rights gate is intentionally outside this module: callers must pass only
permission-approved candidates. Results are revalidated by the Flask API.
"""
from __future__ import annotations

from typing import Any
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # Environment variables can also be supplied by the shell.


def optimize_datasets(candidates: list[dict[str, Any]], budget: float, *, prefer_remote: bool | None = None) -> dict[str, Any]:
    """Maximise total value_score without exceeding budget.

    This deterministic local solver is intended for a hackathon prototype.
    It uses exact subset enumeration up to 22 candidates and a deterministic
    value/cost heuristic for larger catalogues.
    """
    if budget < 0:
        raise ValueError("budget must be non-negative")

    clean = []
    for item in candidates:
        cost = float(item.get("licensing_cost", 0))
        value = float(item.get("value_score", 0))
        if cost < 0 or value < 0:
            raise ValueError("candidate costs and values must be non-negative")
        clean.append({
            "dataset_id": str(item["dataset_id"]),
            "licensing_cost": cost,
            "value_score": value,
        })

    # Remote QpiAI Opt is explicitly opt-in. Rights validation must happen
    # before this function is called, and the caller still revalidates results.
    if prefer_remote is None:
        prefer_remote = os.getenv("QPIAI_OPT_MODE", "local").strip().lower() == "remote"
    if prefer_remote and clean:
        try:
            from optimization.qpiai_adapter import solve_qubo
            # Encode the budget constraint as equality with binary slack bits:
            # sum(cost_i*x_i) + slack = budget. Monetary values are rounded to
            # cents for this prototype. The API result is only a candidate;
            # Backend/app.py independently checks the actual budget.
            scale = 100
            costs = [int(round(x["licensing_cost"] * scale)) for x in clean]
            budget_units = int(round(float(budget) * scale))
            if budget_units > 100000:
                raise ValueError("Remote QUBO budget is too large for the prototype encoding.")
            slack_weights = []
            bit = 1
            while sum(slack_weights) < budget_units and bit <= max(1, budget_units):
                slack_weights.append(bit)
                bit *= 2
            # Limit the final slack bit so its representable range covers budget.
            variable_count = len(clean) + len(slack_weights)
            weights = costs + slack_weights
            penalty = max(1.0, sum(x["value_score"] for x in clean) + 1.0)
            linear = {}
            quadratic = {}
            for i, weight in enumerate(weights):
                linear[i] = penalty * (weight * weight - 2 * budget_units * weight)
            for i in range(len(weights)):
                for j in range(i + 1, len(weights)):
                    quadratic[(i, j)] = 2.0 * penalty * weights[i] * weights[j]
            for i, item in enumerate(clean):
                linear[i] -= item["value_score"] * scale
            remote = solve_qubo(
                variables=variable_count,
                linear_terms=linear,
                quadratic_terms=quadratic,
                budget=budget,
            )
            solution = remote["solution"]
            if len(solution) < len(clean):
                raise RuntimeError("QpiAI Opt returned fewer decision variables than expected.")
            selected = [clean[i] for i in range(len(clean)) if solution[i] == 1]
            selected_cost = sum(x["licensing_cost"] for x in selected)
            selected_value = sum(x["value_score"] for x in selected)
            if selected_cost > budget + 1e-6:
                raise RuntimeError("QpiAI Opt returned a selection over budget; using local fallback.")
            return {
                "status": "COMPLETED",
                "engine": "QPIAI_OPT_QUBO",
                "selected_dataset_ids": [x["dataset_id"] for x in selected],
                "total_cost": round(selected_cost, 6),
                "total_value": round(selected_value, 6),
                "budget": float(budget),
                "message": "Selection returned by QpiAI Opt and validated against the budget.",
                "qpiai_opt": {k: remote.get(k) for k in ("job_id", "problem_id", "energy", "num_evaluations", "credits_used", "execution_time", "status")},
            }
        except Exception as exc:
            # A remote failure must never masquerade as a remote success.
            remote_error = str(exc)[:300]
    else:
        remote_error = None

    if len(clean) <= 22:
        best = []
        best_value = 0.0
        best_cost = 0.0
        for mask in range(1 << len(clean)):
            selected = [clean[i] for i in range(len(clean)) if mask & (1 << i)]
            cost = sum(x["licensing_cost"] for x in selected)
            value = sum(x["value_score"] for x in selected)
            if cost <= budget and (
                value > best_value or
                (value == best_value and cost < best_cost)
            ):
                best, best_cost, best_value = selected, cost, value
        method = "LOCAL_EXACT_KNAPSACK"
    else:
        best, best_cost, best_value = [], 0.0, 0.0
        for item in sorted(
            clean,
            key=lambda x: (x["value_score"] / max(x["licensing_cost"], 0.000001), x["value_score"]),
            reverse=True,
        ):
            if best_cost + item["licensing_cost"] <= budget:
                best.append(item)
                best_cost += item["licensing_cost"]
                best_value += item["value_score"]
        method = "LOCAL_GREEDY_KNAPSACK"

    result = {
        "status": "COMPLETED",
        "engine": method,
        "selected_dataset_ids": [x["dataset_id"] for x in best],
        "total_cost": round(best_cost, 6),
        "total_value": round(best_value, 6),
        "budget": float(budget),
        "message": "Local optimisation ran successfully. This result is not from a remote QpiAI Opt solver.",
    }
    if prefer_remote and clean:
        result["remote_fallback"] = True
        result["remote_error"] = locals().get("remote_error", "Remote optimisation could not be used.")
    return result
