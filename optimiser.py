"""
optimiser.py
------------
Simplex optimiser + 3/6/12-month ramp simulator
Bucket set now includes 1_30.
"""

from __future__ import annotations
from typing import Dict, List, Tuple
from ortools.linear_solver import pywraplp

# ----- global bucket order --------------------------------------------------
BUCKETS = ("1_30", "31_60", "61_90", "91_120", "120_plus")

DEFAULT_WEIGHTS = {
    "1_30":    0.8,   # least effort
    "31_60":   1.0,
    "61_90":   1.5,
    "91_120":  2.0,
    "120_plus":4.0,   # hardest to collect
}


# ─────────────────────────────────── ONE-MONTH SOLVER ───────────────────────
def optimise_month(
    bal: Dict[str, float],
    *,
    target_current: float,
    max_120p_ratio: float,
    max_120p_amount: float | None = None,
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return optimal recovery % dict + KPI dict for ONE month."""
    solver = pywraplp.Solver.CreateSolver("HiGHS")
    r = {b: solver.NumVar(0, 1, f"r_{b}") for b in BUCKETS}
    total = sum(bal.values())

    # objective : minimise weighted workload cost
    solver.Minimize(sum(weights[b] * r[b] for b in BUCKETS))

    # constraint 1 – reach Current% target
    projected_current = (
        bal["current"]
        + sum(bal[b] * r[b] for b in BUCKETS)   # recovered cash becomes current
    )
    solver.Add(projected_current >= target_current * total)

    # constraint 2 – keep 120+ below ceiling
    solver.Add(bal["120_plus"] * (1 - r["120_plus"]) <= max_120p_ratio * total)
    if max_120p_amount is not None:
        solver.Add(bal["120_plus"] * (1 - r["120_plus"]) <= max_120p_amount)

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        raise RuntimeError("No feasible plan for given targets.")

    rec = {k: round(r[k].solution_value(), 4) for k in BUCKETS}
    kpi = {
        "current_ratio": round(projected_current.solution_value() / total, 4),
        "pdr_ratio": round(
            bal["120_plus"] * (1 - rec["120_plus"]) / total, 4
        ),
        "cash_recovered": round(sum(bal[b] * rec[b] for b in BUCKETS), 2),
    }
    return rec, kpi


# ───────────────────────────── ROLL-FORWARD (simple ageing) ─────────────────
def roll_forward(bal: Dict[str, float], rec: Dict[str, float],
                 fresh_sales: float) -> Dict[str, float]:
    """
    • Un-collected portion ages one bucket older.
    • Recovered cash is replaced by new CURRENT sales to keep book size.
    • Current → 1_30 ageing is NOT modelled (MVP simplification).
    """
    new120 = bal["120_plus"] * (1 - rec["120_plus"]) + \
             bal["91_120"]  * (1 - rec["91_120"])
    new91  = bal["61_90"]   * (1 - rec["61_90"])
    new61  = bal["31_60"]   * (1 - rec["31_60"])
    new31  = bal["1_30"]    * (1 - rec["1_30"])
    new13  = 0.0
    newcur = bal["current"] + fresh_sales
    return {
        "current":   newcur,
        "1_30":      new13,
        "31_60":     new31,
        "61_90":     new61,
        "91_120":    new91,
        "120_plus":  new120,
    }


# ───────────────────────── MULTI-MONTH SIMULATOR ────────────────────────────
def simulate(
    balances: Dict[str, float],
    months: int,
    *,
    target_current: float,
    max_120p_ratio: float,
) -> List[Dict]:
    """Runs optimise-→roll-forward loop for N periods."""
    history: List[Dict] = []
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

