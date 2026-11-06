"""Robustness: re-run the strategy comparison under many randomly drawn assumption sets,
and an ablation that removes one lever at a time from the combined strategy."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import data, simulation
from .data import Params, Strategy

TIE_TOL = 0.01   # within 1% of the winner's expected total cost counts as a tie

# Ranges sampled uniformly. Supplier-A DRAM fill spans the two published fulfilment
# figures (S6: 35-40% for small OEMs, ~70% for hyperscalers); the DRAM price range spans
# a 5% quarterly decline to a 25% quarterly rise around TrendForce's +10-15% (S2).
RANGES = {
    "fill_A_dram": (0.375, 0.70),
    "fill_A_pmic": (0.65, 0.95),
    "fill_B_dram": (0.60, 0.90),
    "fill_B_pmic": (0.75, 0.95),
    "fill_lta_dram": (0.80, 0.97),
    "lta_premium": (0.05, 0.30),
    "dram_qoq": (-0.05, 0.25),
    "dram_drift_decay": (0.60, 1.00),
    "contract_to_spot": (0.60, 0.90),
    "broker_markup": (1.00, 1.40),
    "broker_cap": (0.10, 0.50),
    "lead_shift": (-2, 2),            # integer months on A and B lead times
    "demand_vol_mult": (0.5, 1.5),
    "holding_rate_annual": (0.15, 0.35),
    "shock_prob": (0.0, 0.70),
    "init_pipeline_fill_dram": (0.45, 0.80),
    "margin_mult": (0.70, 1.30),
}


def sample_params(rng: np.random.Generator, base: Params | None = None) -> tuple[Params, dict]:
    base = base or Params()
    u = {k: (int(rng.integers(lo, hi + 1)) if k == "lead_shift" else float(rng.uniform(lo, hi)))
         for k, (lo, hi) in RANGES.items()}
    fill = dict(base.fill_mean)
    fill[("A", "DRAM")] = u["fill_A_dram"]
    fill[("A", "PMIC")] = u["fill_A_pmic"]
    fill[("B", "DRAM")] = u["fill_B_dram"]
    fill[("B", "PMIC")] = u["fill_B_pmic"]
    fill[("A_LTA", "DRAM")] = u["fill_lta_dram"]
    pipe = dict(base.init_pipeline_fill)
    pipe["DRAM"] = u["init_pipeline_fill_dram"]
    p = base.with_(
        fill_mean=fill, init_pipeline_fill=pipe,
        lta_premium=u["lta_premium"],
        dram_drift_near=(1 + u["dram_qoq"]) ** (1 / 3) - 1,
        dram_drift_decay=u["dram_drift_decay"],
        contract_to_spot=u["contract_to_spot"],
        broker_markup=u["broker_markup"],
        broker_cap=u["broker_cap"],
        lead_shift=u["lead_shift"],
        demand_common_sd=base.demand_common_sd * u["demand_vol_mult"],
        demand_idio_sd=base.demand_idio_sd * u["demand_vol_mult"],
        holding_rate_annual=u["holding_rate_annual"],
        shock_prob=u["shock_prob"],
        margin_mult=u["margin_mult"],
    )
    return p, u


def classify(summary: pd.DataFrame, rec: str) -> tuple[str, str]:
    """Return (outcome for `rec`, winning strategy) under the standard decision rule."""
    winner, _ = simulation.recommend(summary)
    if winner == rec:
        return "win", winner
    rec_ok = summary.loc[rec, "fill_rate"] >= data.SERVICE_TARGET
    win_ok = summary.loc[winner, "fill_rate"] >= data.SERVICE_TARGET
    close = summary.loc[rec, "total_cost"] <= summary.loc[winner, "total_cost"] * (1 + TIE_TOL)
    if close and (rec_ok or not win_ok):
        return "tie", winner
    return "lose", winner


def robustness(rec: str, n_scenarios: int = 300, runs: int = 1000, seed: int = 7,
               progress=None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_scenarios):
        params, u = sample_params(rng)
        res = simulation.run_all(params, runs=runs, seed=seed * 100_000 + i)
        summ = simulation.summarize(res)
        outcome, winner = classify(summ, rec)
        row = {"scenario": i, "outcome": outcome, "winner": winner,
               "any_meets_target": bool((summ["fill_rate"] >= data.SERVICE_TARGET).any()), **u}
        for k in summ.index:
            row[f"cost_{k}"] = summ.loc[k, "total_cost"]
            row[f"fill_{k}"] = summ.loc[k, "fill_rate"]
        rows.append(row)
        if progress:
            progress((i + 1) / n_scenarios)
    return pd.DataFrame(rows)


def ablation(params: Params | None = None, runs: int = simulation.DEFAULT_RUNS,
             seed: int = simulation.DEFAULT_SEED) -> pd.DataFrame:
    """Remove one lever at a time from strategy (f) to see what drives its result."""
    f = data.STRATEGY_BY_KEY["f"]
    variants = [
        ("Combined hedge (f)", f),
        ("f without broker spot buys", replace(f, emergency_spot=False)),
        ("f without buy-ahead", replace(f, buy_ahead_months=0.0)),
        ("f without LTA (plain A contract)", replace(f, shares={"A": 0.7, "B": 0.3})),
        ("f without supplier B (LTA 100%)", replace(f, shares={"A_LTA": 1.0})),
        ("f with 1-month safety stock", replace(f, ss_months=1.0)),
        ("Status quo + broker spot buys only", replace(data.STRATEGY_BY_KEY["a"], emergency_spot=True)),
    ]
    params = params or Params()
    draws = simulation.make_draws(params, runs, seed)
    rows = []
    for name, s in variants:
        r = simulation.simulate(s, params, draws)
        rows.append({"variant": name, "fill_rate": r["fill_rate"].mean(),
                     "stockout_prob": r["stockout_prob"].mean(), "line_down": r["line_down"].mean(),
                     "total_cost": r["total_cost"].mean(), "landed_cost": r["landed_cost"].mean(),
                     "holding_cost": r["holding_cost"].mean(), "lost_revenue": r["lost_revenue"].mean()})
    return pd.DataFrame(rows)
