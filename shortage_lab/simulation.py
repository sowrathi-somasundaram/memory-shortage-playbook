"""Monte Carlo simulation of sourcing strategies under memory allocation.

All strategies are evaluated on the SAME random draws (common random numbers), so
differences between strategies come from the decisions, not from sampling luck.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import data, model
from .data import COMPONENTS, SUPPLIERS, Params, Strategy

DEFAULT_RUNS = 10_000
DEFAULT_SEED = 2026
STOCKOUT_TOL = 0.995      # a site-month counts as a stockout if < 99.5% of demand is built
LINE_DOWN = 0.80          # "line-down" month: under 80% of demand built


@dataclass
class Draws:
    demand_mult: np.ndarray    # (R, T, P, K)
    fill: np.ndarray           # (R, T, S, C) allocation fill fraction before shocks
    lead_u: np.ndarray         # (R, T, S, C) uniforms for lead-time sampling
    price_eps: np.ndarray      # (R, T, C) standard normals for price paths
    shock_month: np.ndarray    # (R,) month the allocation shock starts (horizon = never)

    @property
    def runs(self) -> int:
        return self.fill.shape[0]


def make_draws(params: Params, runs: int = DEFAULT_RUNS, seed: int = DEFAULT_SEED) -> Draws:
    rng = np.random.default_rng(seed)
    T, P, K = params.horizon, len(data.PRODUCTS), len(data.SITES)
    S, C = len(SUPPLIERS), len(COMPONENTS)

    # Demand: AR(1) common factor + idiosyncratic noise, lognormal with mean 1.
    common = np.zeros((runs, T))
    eps = rng.standard_normal((runs, T))
    rho, sd_c = params.demand_common_rho, params.demand_common_sd
    common[:, 0] = sd_c * eps[:, 0]
    for t in range(1, T):
        common[:, t] = rho * common[:, t - 1] + np.sqrt(1 - rho**2) * sd_c * eps[:, t]
    idio = params.demand_idio_sd * rng.standard_normal((runs, T, P, K))
    total_var = sd_c**2 + params.demand_idio_sd**2
    demand_mult = np.exp(common[:, :, None, None] + idio - total_var / 2)

    fill = np.empty((runs, T, S, C))
    k = params.fill_concentration
    for si, s in enumerate(SUPPLIERS):
        for ci, c in enumerate(COMPONENTS):
            m = params.fill_mean[(s, c)]
            fill[:, :, si, ci] = rng.beta(m * k, (1 - m) * k, size=(runs, T))

    lead_u = rng.random((runs, T, S, C))
    price_eps = rng.standard_normal((runs, T, C))
    hit = rng.random(runs) < params.shock_prob
    shock_month = np.where(hit, rng.integers(0, T, size=runs), T)
    return Draws(demand_mult, fill, lead_u, price_eps, shock_month)


def price_paths(params: Params, draws: Draws) -> np.ndarray:
    """Contract price per component (R, T, C): lognormal random walk around a drift path."""
    T = params.horizon
    t = np.arange(T)
    dram_drift = np.where(t < 3, params.dram_drift_near,
                          params.dram_drift_near * params.dram_drift_decay ** (t - 2))
    drift = np.stack([dram_drift, np.full(T, params.pmic_drift)], axis=1)            # (T, C)
    sd = np.array([params.dram_price_sd, params.pmic_price_sd])
    step = np.log1p(drift)[None] + sd * draws.price_eps - sd**2 / 2
    step[:, 0, :] = 0.0                                                               # month 0 = today
    return params.contract_price0() * np.exp(np.cumsum(step, axis=1))


def supplier_price(supplier: str, contract: np.ndarray, params: Params) -> np.ndarray:
    if supplier == "A":
        return contract
    if supplier == "A_LTA":
        return contract * (1 + params.lta_premium)
    if supplier == "B":
        return contract * params.price_mult_B
    return contract / params.contract_to_spot * params.broker_markup                 # broker: spot x markup


def simulate(strategy: Strategy, params: Params, draws: Draws, keep_paths: bool = False) -> dict:
    R, T = draws.runs, params.horizon
    C, K = len(COMPONENTS), len(data.SITES)
    bom = data.bom()
    base = data.base_demand()                                   # (P, K)
    mu = data.component_demand()                                # (C,)
    mu_site = bom.T @ base                                      # (C, K)
    prices = data.PRODUCTS["price"].to_numpy()
    contrib = (prices - data.PRODUCTS["other_var_cost"].to_numpy()) * params.margin_mult
    h_month = params.holding_rate_annual / 12
    L = params.max_lead() + 2
    contract = price_paths(params, draws)                       # (R, T, C)
    sidx = {s: i for i, s in enumerate(SUPPLIERS)}
    lead_draw = {(s, c): model.sample_discrete(draws.lead_u[:, :, sidx[s], ci], params.lead_dist(s, c))
                 for s in SUPPLIERS for ci, c in enumerate(COMPONENTS)}
    rows = np.arange(R)

    arrivals = np.zeros((R, T + L, C))
    arr_cost = np.zeros((R, T + L, C))
    # Pipeline already on order from supplier A before month 0, at the reduced historic allocation.
    for ci, c in enumerate(COMPONENTS):
        dist = params.lead_dist("A", c)
        for t in range(T + L):
            p_late = sum(v for lag, v in dist.items() if lag > t)
            q = params.init_pipeline_fill[c] * mu[ci] * p_late
            arrivals[:, t, ci] += q
            arr_cost[:, t, ci] += q * params.contract_price0()[ci] * (1 + params.freight_pct_std)

    inv = np.broadcast_to(params.init_onhand_months * mu_site, (R, C, K)).copy()
    target_site = (1 + strategy.ss_months) * mu_site
    mean_lead = np.array([sum(sh * params.mean_lead(s, c) for s, sh in strategy.shares.items())
                          for c in COMPONENTS])
    order_level = (mean_lead + 1 + strategy.ss_months) * mu                         # (C,)
    ba_remaining = np.full((R, C), strategy.buy_ahead_months) * mu
    ba_price = supplier_price("C", contract[:, 0, :], params)                       # locked at t=0

    demand_tot = produced_tot = lost_rev = lost_contrib = 0.0
    landed = np.zeros(R)
    holding = np.zeros(R)
    received = np.zeros((R, C))
    consumed = np.zeros((R, C))
    initial_onhand = inv.sum(axis=2).copy()
    stockout_months = np.zeros(R)
    line_down = np.zeros(R, bool)
    paths = {"fill": np.zeros((R, T)), "cover": np.zeros((R, T, C))} if keep_paths else None

    def book(sup: str, t: int, qty: np.ndarray, ci: int, unit_price: np.ndarray, freight: float,
             usable: float = 1.0) -> None:
        """Place a confirmed order (R,) for component ci; it arrives after a sampled lead time."""
        lag = lead_draw[(sup if sup != "A_LTA" else "A", COMPONENTS[ci])][:, t]
        idx = np.minimum(t + lag, T + L - 1)
        np.add.at(arrivals[:, :, ci], (rows, idx), qty * usable)
        np.add.at(arr_cost[:, :, ci], (rows, idx), qty * unit_price * (1 + freight))

    for t in range(T):
        # 1. receive
        inv += model.split_arrivals(arrivals[:, t, :], inv, target_site)
        received += arrivals[:, t, :]
        landed += arr_cost[:, t, :].sum(axis=1)

        # 2. build
        demand = base[None] * draws.demand_mult[:, t]                              # (R, P, K)
        frac, use = model.produce(inv, demand, bom)
        inv -= use
        consumed += use.sum(axis=2)
        unmet = demand * (1 - frac[:, None, :])                                     # (R, P, K)
        demand_tot = demand_tot + demand.sum(axis=(1, 2))
        produced_tot = produced_tot + (demand - unmet).sum(axis=(1, 2))
        lost_rev = lost_rev + np.einsum("rpk,p->r", unmet, prices)
        lost_contrib = lost_contrib + np.einsum("rpk,p->r", unmet, contrib)
        stockout_months += (frac < STOCKOUT_TOL).sum(axis=1)
        line_down |= (frac < LINE_DOWN).any(axis=1)

        # 3. hold
        holding += h_month * np.einsum("rck,rc->r", inv, contract[:, t, :])
        if keep_paths:
            paths["fill"][:, t] = (demand - unmet).sum(axis=(1, 2)) / demand.sum(axis=(1, 2))
            paths["cover"][:, t] = inv.sum(axis=2) / mu

        # 4. order
        shocked = t >= draws.shock_month                                            # (R,)
        pipeline = arrivals[:, t + 1:, :].sum(axis=1)
        position = inv.sum(axis=2) + pipeline                                       # (R, C)
        need = model.order_up_to(position, order_level)
        for ci in range(C):
            broker_room = params.broker_cap * mu[ci] * np.ones(R)
            for sup, share in strategy.shares.items():
                si = sidx[sup]
                alloc_base = share * mu[ci]
                req = share * need[:, ci]
                if sup == "A_LTA":
                    req = np.maximum(req, params.lta_commit * alloc_base)
                    mult = np.where(shocked, params.shock_mult_lta, 1.0)
                else:
                    mult = np.where(shocked, params.shock_mult, 1.0)
                fill = draws.fill[:, t, si, ci] * mult
                qty = model.confirm_order(req, alloc_base, fill, params.order_inflation_cap)
                price = supplier_price(sup, contract[:, t, ci], params)
                book(sup, t, qty, ci, price, params.freight_pct_std)

            # buy-ahead: broker tranches at the price locked in month 0
            if strategy.buy_ahead_months > 0:
                tranche = np.minimum(ba_remaining[:, ci], broker_room) * draws.fill[:, t, sidx["C"], ci]
                ba_remaining[:, ci] -= tranche
                broker_room = broker_room - tranche
                book("C", t, tranche, ci, ba_price[:, ci], params.freight_pct_std,
                     usable=1 - params.broker_reject)

            # emergency spot buy when next month's cover is below half a month
            if strategy.emergency_spot:
                projected = inv[:, ci, :].sum(axis=1) + arrivals[:, t + 1, ci]
                gap = np.where(projected < 0.5 * mu[ci], 2.0 * mu[ci] - projected, 0.0)
                qty = np.minimum(gap, broker_room) * draws.fill[:, t, sidx["C"], ci]
                price = supplier_price("C", contract[:, t, ci], params)
                book("C", t, qty, ci, price, params.freight_pct_air, usable=1 - params.broker_reject)

    ending_value = np.einsum("rck,rc->r", inv, contract[:, T - 1, :])
    out = {
        "fill_rate": produced_tot / demand_tot,
        "stockout_prob": stockout_months / (T * K),
        "line_down": line_down.astype(float),
        "landed_cost": landed,
        "holding_cost": holding,
        "lost_revenue": lost_rev,
        "lost_contribution": lost_contrib,
        "ending_inventory_value": ending_value,
        "total_cost": landed + holding + lost_contrib - ending_value,
        "final_onhand": inv,
        "initial_onhand": initial_onhand,
        "received": received,
        "consumed": consumed,
    }
    if keep_paths:
        out["paths"] = paths
    return out


def run_all(params: Params | None = None, runs: int = DEFAULT_RUNS, seed: int = DEFAULT_SEED,
            strategies: list[Strategy] | None = None, keep_paths: bool = False) -> dict[str, dict]:
    params = params or Params()
    draws = make_draws(params, runs, seed)
    return {s.key: simulate(s, params, draws, keep_paths) for s in (strategies or data.STRATEGIES)}


METRICS = ["fill_rate", "stockout_prob", "line_down", "landed_cost", "holding_cost",
           "lost_revenue", "lost_contribution", "ending_inventory_value", "total_cost"]


def summarize(results: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for key, r in results.items():
        row = {"key": key, "strategy": data.STRATEGY_BY_KEY[key].name}
        for m in METRICS:
            row[m] = float(np.mean(r[m]))
        row["total_cost_p5"] = float(np.percentile(r["total_cost"], 5))
        row["total_cost_p95"] = float(np.percentile(r["total_cost"], 95))
        row["fill_rate_p5"] = float(np.percentile(r["fill_rate"], 5))
        row["p_fill_ge_target"] = float(np.mean(r["fill_rate"] >= data.SERVICE_TARGET))
        rows.append(row)
    return pd.DataFrame(rows).set_index("key")


def recommend(summary: pd.DataFrame, target: float = data.SERVICE_TARGET) -> tuple[str, bool]:
    """Decision rule fixed before looking at results: lowest expected total cost among
    strategies whose mean fill rate meets the target. If none qualifies, lowest cost overall.

    Returns (strategy key, whether the service target was met).
    """
    ok = summary[summary["fill_rate"] >= target]
    if len(ok):
        return ok["total_cost"].idxmin(), True
    return summary["total_cost"].idxmin(), False
