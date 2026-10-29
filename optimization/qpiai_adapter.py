"""QpiAI Opt REST adapter based on the team's supplied API documentation.

Remote execution is opt-in via QPIAI_OPT_MODE=remote. A JWT is read only from
QPIAI_OPT_API_KEY; never print or include it in errors/logs.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

try:
    from dotenv import load_dotenv
    # Project-root .env when run from the repository root; harmless if absent.
    load_dotenv()
except ImportError:  # Environment variables can still be set by the shell.
    pass

BASE_URL = os.getenv("QPIAI_OPT_BASE_URL", "https://opt-server.qpiai.tech/api").rstrip("/")


def is_configured() -> bool:
    return bool(os.getenv("QPIAI_OPT_API_KEY"))


def is_remote_mode() -> bool:
    return os.getenv("QPIAI_OPT_MODE", "local").strip().lower() == "remote"


def _headers() -> dict[str, str]:
    token = os.getenv("QPIAI_OPT_API_KEY", "").strip()
    if not token:
        raise RuntimeError("QpiAI Opt token is missing; set QPIAI_OPT_API_KEY in .env.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _request(method: str, path: str, *, timeout: float = 20, **kwargs):
    try:
        response = requests.request(method, f"{BASE_URL}{path}", headers=_headers(), timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach QpiAI Opt ({type(exc).__name__}).") from None
    if not response.ok:
        # Do not include response request headers or secrets in errors.
        detail = ""
        try:
            payload = response.json()
            detail = str(payload.get("detail") or payload.get("message") or payload.get("error") or "")[:300]
        except (ValueError, AttributeError):
            detail = response.text[:200]
        raise RuntimeError(f"QpiAI Opt returned HTTP {response.status_code}" + (f": {detail}" if detail else "."))
    try:
        return response.json()
    except ValueError:
        raise RuntimeError("QpiAI Opt returned a non-JSON response.") from None


def solve_qubo(*, variables, linear_terms, quadratic_terms, budget=None) -> dict[str, Any]:
    """Create a QUBO problem, submit a job, poll it, and return its solution.

    `variables` is the number of binary variables. Terms are dictionaries keyed
    by integer indices/pairs, e.g. {0: -2.0}, {(0, 1): 1.5}.
    """
    if not is_configured():
        raise RuntimeError("QpiAI Opt token is missing; set QPIAI_OPT_API_KEY in .env.")
    experiment_id = os.getenv("QPIAI_OPT_EXPERIMENT_ID", "").strip()
    if not experiment_id:
        raise RuntimeError("Set QPIAI_OPT_EXPERIMENT_ID to an experiment UUID from your QpiAI Opt account.")

    qubo: dict[str, float] = {}
    for index, coefficient in linear_terms.items():
        i = int(index)
        qubo[f"{i},{i}"] = float(coefficient)
    for pair, coefficient in quadratic_terms.items():
        i, j = pair
        i, j = int(i), int(j)
        key = f"{min(i, j)},{max(i, j)}"
        qubo[key] = qubo.get(key, 0.0) + float(coefficient)

    problem_payload = {
        "name": "ArcVault Dataset Selection",
        "method": "QUBO",
        "num_variables": int(variables),
        "qubo_dict": qubo,
        "max_evaluations": int(os.getenv("QPIAI_OPT_MAX_EVALUATIONS", "1000")),
        "solver_config": {"penalty": float(os.getenv("QPIAI_OPT_SOLVER_PENALTY", "1.0"))},
    }
    created = _request("POST", "/problems/create", json=problem_payload)
    problem_id = created.get("id")
    if not problem_id:
        raise RuntimeError("QpiAI Opt created a response without a problem ID.")

    job_payload: dict[str, Any] = {"problem_id": problem_id, "experiment_id": experiment_id}
    compute_resource_id = os.getenv("QPIAI_OPT_COMPUTE_RESOURCE_ID", "").strip()
    if compute_resource_id:
        job_payload["compute_resource_id"] = compute_resource_id
    job = _request("POST", "/jobs/opt", json=job_payload)
    job_data = job.get("job", job)
    job_id = job_data.get("id")
    if not job_id:
        raise RuntimeError("QpiAI Opt accepted a job response without a job ID.")

    timeout_seconds = max(5, int(os.getenv("QPIAI_OPT_TIMEOUT_SECONDS", "120")))
    poll_seconds = max(1, float(os.getenv("QPIAI_OPT_POLL_SECONDS", "2")))
    deadline = time.monotonic() + timeout_seconds
    terminal_success = {"success", "succeeded", "completed", "complete"}
    terminal_failure = {"failed", "failure", "error", "cancelled", "canceled"}
    while True:
        current = _request("GET", f"/jobs/{job_id}")
        status = str(current.get("status", "")).strip().lower()
        if status in terminal_success:
            break
        if status in terminal_failure:
            message = current.get("error") or f"job status was {current.get('status')}"
            raise RuntimeError(f"QpiAI Opt job failed: {str(message)[:300]}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for QpiAI Opt job {job_id}; latest status: {current.get('status', 'unknown')}.")
        time.sleep(poll_seconds)

    raw_solution = current.get("server_response", "")
    if isinstance(raw_solution, str):
        try:
            raw_solution = json.loads(raw_solution)
        except ValueError:
            raise RuntimeError("QpiAI Opt job succeeded but server_response was not valid JSON.") from None
    if not isinstance(raw_solution, dict) or not isinstance(raw_solution.get("solution"), list):
        raise RuntimeError("QpiAI Opt job succeeded but no solution array was returned.")
    return {
        "solution": [int(value) for value in raw_solution["solution"]],
        "energy": raw_solution.get("energy"),
        "num_evaluations": raw_solution.get("num_evaluations"),
        "job_id": job_id,
        "problem_id": problem_id,
        "credits_used": current.get("credits_used"),
        "execution_time": current.get("execution_time"),
        "status": current.get("status"),
    }
