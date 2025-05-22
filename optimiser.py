"""
optimiser.py
------------
Simplex optimiser + 3/6/12-month ramp simulator
"""

from __future__ import annotations
from typing import Dict, List, Tuple
from ortools.linear_solver import pywraplp


# ────────────────────────────────────────────────────────────────────────────
# ONE-MONTH LINEAR-PROGRAMMING SOLVER
# ────────────────────────────────────────────────────────────────────────────
def optimise_month(
    bal: Dict[str, float],
    *,
    target_current: float,
    max_120p_ratio: float,
    max_120p_amount: float | None = None,
    weights: Dict[str, float] | None = None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Return optimal recovery % and KPI dict for ONE month.
    bal  ─ dict with keys: current, 31_60, 61_90, 91_120, 120_plus
    """
    if weights is None:
        weights = {"31_60": 1.0, "61_90": 1.5, "91_120": 2.0, "120_plus": 4.0}

    solver = pywraplp.Solver.CreateSolver("HiGHS")
    r = {b: solver.NumVar(0, 1, f"r_{b}") for b in ("31_60", "61_90", "91_120", "120_plus")}
    total = sum(bal.values())

    # Objective: minimise workload cost
    solver.Minimize(sum(weights[b] * r[b] for b in r))

    # Constraint 1 – target Current %
    projected_current = (
        bal["current"]
        + bal["31_60"] * r["31_60"]
        + bal["61_90"] * r["61_90"]
        + bal["91_120"] * r["91_120"]
        + bal["120_plus"] * r["120_plus"]
    )
    solver.Add(projected_current >= target_current * total)

    # Constraint 2 – cap 120-plus %
    solver.Add(bal["120_plus"] * (1 - r["120_plus"]) <= max_120p_ratio * total)
    if max_120p_amount is not None:  # optional absolute cap
        solver.Add(bal["120_plus"] * (1 - r["120_plus"]) <= max_120p_amount)

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        raise RuntimeError("No feasible plan for given targets.")

    rec = {k: round(r[k].solution_value(), 4) for k in r}
    kpi = {
        "current_ratio": round(projected_current.solution_value() / total, 4),
        "pdr_ratio": round(bal["120_plus"] * (1 - rec["120_plus"]) / total, 4),
        "cash_recovered": round(sum(bal[b] * rec.get(b, 0) for b in rec), 2),
    }
    return rec, kpi


# ────────────────────────────────────────────────────────────────────────────
# PORTFOLIO ROLL-FORWARD (simple ageing model)
# ────────────────────────────────────────────────────────────────────────────
def roll_forward(bal: Dict[str, float], rec: Dict[str, float], fresh_sales: float) -> Dict[str, float]:
    """
    • Un-collected portion of each bucket slides one step older.
    • Recovered cash is replaced by NEW current sales (keeps book size constant).
    """
    new120 = bal["120_plus"] * (1 - rec["120_plus"]) + bal["91_120"] * (1 - rec["91_120"])
    new91  = bal["61_90"]   * (1 - rec["61_90"])
    new61  = bal["31_60"]   * (1 - rec["31_60"])
    new31  = 0.0  # ignoring current slippage for MVP
    newcur = bal["current"] + fresh_sales
    return {"current": newcur, "31_60": new31, "61_90": new61, "91_120": new91, "120_plus": new120}


# ────────────────────────────────────────────────────────────────────────────
# MULTI-MONTH SIMULATOR
# ────────────────────────────────────────────────────────────────────────────
def simulate(
    balances: Dict[str, float],
    months: int,
    *,
    target_current: float,
    max_120p_ratio: float,
) -> List[Dict]:
    """
    Runs optimise-→roll-forward for N months.
    Returns list with month-by-month dictionaries.
    """
    history = []
    bal = balances.copy()
    for m in range(1, months + 1):
        rec, kpi = optimise_month(
            bal,
            target_current=target_current,
            max_120p_ratio=max_120p_ratio,
        )
        history.append({"month": m, "balances": bal, "recoveries": rec, "kpi": kpi})
        bal = roll_forward(bal, rec, kpi["cash_recovered"])
    return history
