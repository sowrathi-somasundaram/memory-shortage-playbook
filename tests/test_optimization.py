import itertools

import pandas as pd
import pulp
import pytest

from shortage_lab import data, optimization as opt


@pytest.mark.parametrize("slip", list(opt.SLIP_SCENARIOS.values()))
def test_award_meets_every_constraint(slip):
    res = opt.solve_award(slip)
    assert res.status == "Optimal"
    assert opt.check_award(res, slip) == []


@pytest.mark.parametrize("slip", list(opt.SLIP_SCENARIOS.values()))
def test_optimized_never_worse_than_incumbent(slip):
    res = opt.solve_award(slip)
    assert res.total_cost <= opt.incumbent_cost(slip)["total_cost"] + 1e-6


def test_air_use_grows_with_slip_until_air_cannot_help():
    sweep = opt.slip_sweep()
    assert (sweep["air_loads"] >= sweep["urgent_loads"] - sweep["unrecoverable_loads"]).all()
    assert sweep["air_loads"].iloc[2] > sweep["air_loads"].iloc[0]
    # unavoidable lateness rises monotonically with the slip
    assert sweep["late_even_by_air"].is_monotonic_increasing


def test_tighter_service_target_never_cheaper():
    base = opt.solve_award(1.0, on_time_target=0.90).total_cost
    tight = opt.solve_award(1.0, on_time_target=0.95).total_cost
    assert tight >= base - 1e-6


def test_urgent_shares_are_probabilities():
    for slip in [0.5, 3, 10, 30]:
        df = opt.urgent_and_late_share(slip)
        assert ((df["urgent_share"] >= 0) & (df["urgent_share"] + df["late_share"] <= 1 + 1e-12)).all()
        unexposed = data.LANES["slip_exposed"] == 0
        assert (df.loc[unexposed, ["urgent_share", "late_share"]] == 0).all().all()


def test_matches_brute_force_on_small_instance():
    """On a 2-lane toy problem, the MIP optimum equals exhaustive enumeration."""
    lanes = pd.DataFrame({"lane": ["L1", "L2"], "miles": [600, 900], "loads_per_month": [5, 4],
                          "buffer_days": [5, 5], "truck_days": [2, 2], "air_days": [1, 1],
                          "slip_exposed": [1, 1]})
    bids = pd.DataFrame([
        ("T1 (incumbent)", "truck", "L1", 1000, 5, 0.94), ("T2", "truck", "L1", 900, 5, 0.91),
        ("T1 (incumbent)", "truck", "L2", 1500, 4, 0.94), ("T3", "truck", "L2", 1300, 4, 0.87),
        ("Air X1", "air", "L1", 9000, 14, 0.97), ("Air X1", "air", "L2", 9500, 14, 0.97),
    ], columns=["carrier", "mode", "lane", "cost_per_load", "lane_capacity", "on_time"])
    slip = 3.0
    res = opt.solve_award(slip, bids=bids, lanes=lanes, on_time_target=0.92)
    need = opt.urgent_and_late_share(slip, lanes).set_index("lane")
    best = float("inf")
    groups = {l: bids[bids["lane"] == l].reset_index(drop=True) for l in lanes["lane"]}
    def splits(l, vol):
        g = groups[l]
        for combo in itertools.product(range(vol + 1), repeat=len(g)):
            if sum(combo) != vol or any(c > cap for c, cap in zip(combo, g["lane_capacity"])):
                continue
            if sum(c * o for c, o in zip(combo, g["on_time"])) < 0.92 * vol - 1e-9:
                continue
            if sum(c for c, m in zip(combo, g["mode"]) if m == "air") < need.loc[l, "urgent_loads"]:
                continue
            yield combo, sum(c * p for c, p in zip(combo, g["cost_per_load"]))
    # lanes are independent here except the shared air capacity (14), which never binds
    best = sum(min(cost for _, cost in splits(l, int(v))) for l, v in
               zip(lanes["lane"], lanes["loads_per_month"]))
    assert res.freight_cost == pytest.approx(best)


def test_solver_available():
    assert "PULP_CBC_CMD" in pulp.listSolvers(onlyAvailable=True)
