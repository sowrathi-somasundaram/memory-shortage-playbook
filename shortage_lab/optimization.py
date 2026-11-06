"""Freight procurement: award carrier bids by lane at minimum cost (integer program, PuLP/CBC).

Constraints
  * every lane's monthly loads are fully awarded
  * carrier capacity per lane and across lanes
  * volume-weighted on-time rate per lane >= target
  * truck diversification: no truck carrier above MAX_LANE_SHARE of a lane with >= 10 loads
  * urgent loads (those a truck can no longer deliver inside the lane's buffer after an
    upstream lead-time slip) must move by air; urgent loads air capacity cannot cover are
    recorded as unrecoverable and charged LATE_PENALTY
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pulp
from scipy import stats

from . import data

SLIP_SCENARIOS = {"On plan (mean slip 1 day)": 1.0, "Minor slip (3 days)": 3.0,
                  "Major slip (5 days)": 5.0, "Severe slip (8 days)": 8.0}
SLIP_SHAPE = 2.0   # HYP: upstream delay ~ Gamma(shape=2, mean=slip)


def urgent_and_late_share(mean_slip: float, lanes: pd.DataFrame = data.LANES) -> pd.DataFrame:
    """Share of each lane's loads that (i) must fly to arrive on time, (ii) are late even by air.

    Upstream delay D ~ Gamma. A load is urgent if truck would miss the buffer but air would
    not; it is unavoidably late if even air misses. Lanes not exposed to supplier slip
    (warehouse -> local plant) have neither.
    """
    d = stats.gamma(a=SLIP_SHAPE, scale=mean_slip / SLIP_SHAPE)
    exposed = lanes["slip_exposed"].to_numpy()
    late = np.asarray(d.sf(lanes["buffer_days"] - lanes["air_days"])) * exposed
    truck_late = np.asarray(d.sf(lanes["buffer_days"] - lanes["truck_days"])) * exposed
    out = lanes[["lane", "loads_per_month"]].copy()
    out["urgent_share"] = np.clip(truck_late - late, 0, 1)
    out["late_share"] = late
    out["urgent_loads"] = np.ceil(out["urgent_share"] * out["loads_per_month"] - 1e-9).astype(int)
    out["late_loads"] = np.round(out["late_share"] * out["loads_per_month"]).astype(int)
    return out


@dataclass
class AwardResult:
    status: str
    award: pd.DataFrame          # carrier, lane, loads, cost
    lane_summary: pd.DataFrame
    total_cost: float
    freight_cost: float
    penalty_cost: float


def solve_award(mean_slip: float = 1.0, bids: pd.DataFrame | None = None,
                lanes: pd.DataFrame = data.LANES, on_time_target: float = data.ON_TIME_TARGET,
                max_share: float = data.MAX_LANE_SHARE) -> AwardResult:
    bids = data.carrier_bids() if bids is None else bids
    need = urgent_and_late_share(mean_slip, lanes).set_index("lane")
    cap_total = data.CARRIERS.set_index("carrier")["monthly_capacity"]

    prob = pulp.LpProblem("carrier_award", pulp.LpMinimize)
    x = {(r.carrier, r.lane): pulp.LpVariable(f"x_{i}", lowBound=0, upBound=r.lane_capacity, cat="Integer")
         for i, r in enumerate(bids.itertuples())}
    unrec = {l: pulp.LpVariable(f"u_{j}", lowBound=0, cat="Integer") for j, l in enumerate(lanes["lane"])}
    cost = {(r.carrier, r.lane): r.cost_per_load for r in bids.itertuples()}
    on_time = {(r.carrier, r.lane): r.on_time for r in bids.itertuples()}
    mode = {(r.carrier, r.lane): r.mode for r in bids.itertuples()}

    prob += pulp.lpSum(cost[k] * v for k, v in x.items()) + data.LATE_PENALTY * pulp.lpSum(unrec.values())
    for lane in lanes.itertuples():
        keys = [k for k in x if k[1] == lane.lane]
        vol = lane.loads_per_month
        prob += pulp.lpSum(x[k] for k in keys) == vol, f"volume_{lane.Index}"
        prob += pulp.lpSum(on_time[k] * x[k] for k in keys) >= on_time_target * vol, f"ontime_{lane.Index}"
        air = [k for k in keys if mode[k] == "air"]
        urgent = int(need.loc[lane.lane, "urgent_loads"])
        if urgent:
            prob += pulp.lpSum(x[k] for k in air) + unrec[lane.lane] >= urgent, f"urgent_{lane.Index}"
        else:
            prob += unrec[lane.lane] == 0
        if vol >= 10:
            for k in keys:
                if mode[k] == "truck":
                    prob += x[k] <= max_share * vol, f"share_{lane.Index}_{k[0]}"
    for carrier in bids["carrier"].unique():
        prob += pulp.lpSum(v for k, v in x.items() if k[0] == carrier) <= cap_total[carrier], f"cap_{carrier}"

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]
    award = pd.DataFrame([{"carrier": k[0], "lane": k[1], "mode": mode[k], "loads": int(round(v.value() or 0)),
                           "cost_per_load": cost[k], "on_time": on_time[k]} for k, v in x.items()])
    award["cost"] = award["loads"] * award["cost_per_load"]
    award = award[award["loads"] > 0].reset_index(drop=True)
    lane_summary = need.reset_index()
    lane_summary["unrecoverable_loads"] = [int(round(unrec[l].value() or 0)) for l in lane_summary["lane"]]
    lane_summary["air_loads"] = [int(award.query("lane == @l and mode == 'air'")["loads"].sum())
                                 for l in lane_summary["lane"]]
    lane_summary["freight_cost"] = [award.query("lane == @l")["cost"].sum() for l in lane_summary["lane"]]
    lane_summary["on_time_rate"] = [
        (award.query("lane == @l")["loads"] * award.query("lane == @l")["on_time"]).sum()
        / max(1, award.query("lane == @l")["loads"].sum()) for l in lane_summary["lane"]]
    freight = float(award["cost"].sum())
    penalty = float(data.LATE_PENALTY * (lane_summary["unrecoverable_loads"].sum()
                                         + lane_summary["late_loads"].sum()))
    return AwardResult(status, award, lane_summary, freight + penalty, freight, penalty)


def incumbent_cost(mean_slip: float = 1.0, bids: pd.DataFrame | None = None,
                   lanes: pd.DataFrame = data.LANES) -> dict:
    """Benchmark: today's routing guide. The incumbent truck carrier hauls every load it
    can on time; urgent loads are bought from the cheapest air bid at a spot premium.
    Air capacity limits still apply, so overflow is unrecoverable (same penalty)."""
    bids = data.carrier_bids() if bids is None else bids
    need = urgent_and_late_share(mean_slip, lanes).set_index("lane")
    inc = bids[bids["carrier"] == "T1 (incumbent)"].set_index("lane")["cost_per_load"]
    air = bids[bids["mode"] == "air"]
    air_cap = data.CARRIERS.set_index("carrier")["monthly_capacity"].to_dict()
    truck = spot_air = 0.0
    unrecoverable = 0
    # serve lanes with the largest urgent volume first, cheapest air carrier first
    for lane in lanes.sort_values("loads_per_month", ascending=False).itertuples():
        urgent = int(need.loc[lane.lane, "urgent_loads"])
        options = air[air["lane"] == lane.lane].sort_values("cost_per_load")
        flown = 0
        for o in options.itertuples():
            take = min(urgent - flown, air_cap[o.carrier])
            air_cap[o.carrier] -= take
            flown += take
            spot_air += take * o.cost_per_load * (1 + data.AIR_SPOT_PREMIUM)
        unrecoverable += urgent - flown
        truck += (lane.loads_per_month - flown) * inc[lane.lane]
    late = int(need["late_loads"].sum())
    penalty = (unrecoverable + late) * data.LATE_PENALTY
    return {"truck_cost": truck, "air_cost": spot_air, "penalty_cost": penalty,
            "unrecoverable_loads": unrecoverable, "late_loads": late,
            "total_cost": truck + spot_air + penalty}


def check_award(result: AwardResult, mean_slip: float, bids: pd.DataFrame | None = None,
                lanes: pd.DataFrame = data.LANES, on_time_target: float = data.ON_TIME_TARGET,
                max_share: float = data.MAX_LANE_SHARE) -> list[str]:
    """Independent constraint audit of an award; returns a list of violations (empty = OK)."""
    bids = data.carrier_bids() if bids is None else bids
    need = urgent_and_late_share(mean_slip, lanes).set_index("lane")
    a = result.award.merge(bids[["carrier", "lane", "lane_capacity"]], on=["carrier", "lane"], how="left")
    issues = []
    if a["lane_capacity"].isna().any():
        issues.append("award to a carrier that did not bid the lane")
    for lane in lanes.itertuples():
        sub = a[a["lane"] == lane.lane]
        vol = lane.loads_per_month
        if sub["loads"].sum() != vol:
            issues.append(f"{lane.lane}: awarded {sub['loads'].sum()} of {vol} loads")
        if (sub["loads"] * sub["on_time"]).sum() < on_time_target * vol - 1e-6:
            issues.append(f"{lane.lane}: on-time below target")
        if (sub["loads"] > sub["lane_capacity"]).any():
            issues.append(f"{lane.lane}: lane capacity exceeded")
        if vol >= 10 and (sub.loc[sub["mode"] == "truck", "loads"] > max_share * vol + 1e-6).any():
            issues.append(f"{lane.lane}: diversification rule broken")
        unrec = int(result.lane_summary.set_index("lane").loc[lane.lane, "unrecoverable_loads"])
        if sub.loc[sub["mode"] == "air", "loads"].sum() + unrec < need.loc[lane.lane, "urgent_loads"]:
            issues.append(f"{lane.lane}: urgent loads not covered")
    cap = data.CARRIERS.set_index("carrier")["monthly_capacity"]
    for carrier, loads in a.groupby("carrier")["loads"].sum().items():
        if loads > cap[carrier]:
            issues.append(f"{carrier}: total capacity exceeded")
    return issues


def slip_sweep(bids: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    for name, slip in SLIP_SCENARIOS.items():
        opt = solve_award(slip, bids)
        inc = incumbent_cost(slip, bids)
        rows.append({
            "scenario": name, "mean_slip_days": slip, "status": opt.status,
            "urgent_loads": int(opt.lane_summary["urgent_loads"].sum()),
            "air_loads": int(opt.lane_summary["air_loads"].sum()),
            "unrecoverable_loads": int(opt.lane_summary["unrecoverable_loads"].sum()),
            "late_even_by_air": int(opt.lane_summary["late_loads"].sum()),
            "optimized_freight": opt.freight_cost, "incumbent_freight": inc["truck_cost"] + inc["air_cost"],
            "optimized_cost": opt.total_cost, "incumbent_cost": inc["total_cost"],
            "savings": inc["total_cost"] - opt.total_cost,
            "savings_pct": (inc["total_cost"] - opt.total_cost) / inc["total_cost"],
            "freight_savings_pct": 1 - opt.freight_cost / (inc["truck_cost"] + inc["air_cost"]),
        })
    return pd.DataFrame(rows)
