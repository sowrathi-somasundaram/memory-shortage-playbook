import json

import numpy as np
import pandas as pd
import pytest

from shortage_lab import data, model, simulation
from shortage_lab.cache import OUT, params_fingerprint

RUNS = 2000


@pytest.fixture(scope="module")
def results():
    return simulation.run_all(runs=RUNS, seed=11)


def test_inventory_balance(results):
    """Opening stock + receipts - consumption = closing stock, for every run and component."""
    for key, r in results.items():
        closing = r["final_onhand"].sum(axis=2)
        expected = r["initial_onhand"] + r["received"] - r["consumed"]
        np.testing.assert_allclose(closing, expected, rtol=1e-9, atol=1e-6, err_msg=key)
        assert (r["final_onhand"] >= -1e-9).all()


def test_seed_reproducibility():
    a = simulation.run_all(runs=500, seed=3)
    b = simulation.run_all(runs=500, seed=3)
    c = simulation.run_all(runs=500, seed=4)
    for k in a:
        np.testing.assert_array_equal(a[k]["total_cost"], b[k]["total_cost"])
        np.testing.assert_array_equal(a[k]["fill_rate"], b[k]["fill_rate"])
    assert not np.array_equal(a["a"]["total_cost"], c["a"]["total_cost"])


def test_metric_ranges_and_cost_identity(results):
    for r in results.values():
        assert ((r["fill_rate"] >= 0) & (r["fill_rate"] <= 1)).all()
        assert ((r["stockout_prob"] >= 0) & (r["stockout_prob"] <= 1)).all()
        for m in ["landed_cost", "holding_cost", "lost_revenue", "lost_contribution", "ending_inventory_value"]:
            assert (r[m] >= 0).all()
        np.testing.assert_allclose(
            r["total_cost"],
            r["landed_cost"] + r["holding_cost"] + r["lost_contribution"] - r["ending_inventory_value"])
        # lost contribution can never exceed lost revenue
        assert (r["lost_contribution"] <= r["lost_revenue"] + 1e-6).all()


def test_no_allocation_means_status_quo_serves_demand():
    """Sanity: with full allocation and a full pipeline, single-sourcing works."""
    p = data.Params()
    fill = {k: 0.999 for k in p.fill_mean}
    p = p.with_(fill_mean=fill, init_pipeline_fill={"DRAM": 1.0, "PMIC": 1.0}, shock_prob=0.0,
                fill_concentration=1000.0)
    r = simulation.run_all(p, runs=500, strategies=[data.STRATEGY_BY_KEY["a"]])["a"]
    assert r["fill_rate"].mean() > 0.97


def test_safety_stock_matters_only_when_supply_is_available():
    """Higher safety stock raises holding cost and service when supply is unconstrained,
    but cannot be built when allocation binds (the model's key structural finding)."""
    loose = data.Params().with_(fill_mean={k: 0.999 for k in data.Params().fill_mean},
                                init_pipeline_fill={"DRAM": 1.0, "PMIC": 1.0}, shock_prob=0.0)
    r = simulation.run_all(loose, runs=500, strategies=[data.STRATEGY_BY_KEY[k] for k in "ad"])
    assert r["d"]["holding_cost"].mean() > 1.2 * r["a"]["holding_cost"].mean()
    assert r["d"]["fill_rate"].mean() >= r["a"]["fill_rate"].mean()
    tight = simulation.run_all(runs=500, strategies=[data.STRATEGY_BY_KEY[k] for k in "ad"])
    assert abs(tight["d"]["fill_rate"].mean() - tight["a"]["fill_rate"].mean()) < 0.01


def test_price_path_matches_drift():
    p = data.Params()
    draws = simulation.make_draws(p, runs=20000, seed=5)
    prices = simulation.price_paths(p, draws)
    np.testing.assert_allclose(prices[:, 0, :], p.contract_price0()[None].repeat(20000, 0))
    # month 3 DRAM mean ~= p0 * (1 + quarterly rise) under the mean-corrected lognormal walk
    expected = p.contract_price0()[0] * (1 + data.MARKET_ANCHORS["dram_q4_contract_qoq"].value)
    assert prices[:, 3, 0].mean() == pytest.approx(expected, rel=0.01)


def test_split_arrivals_conserves_units():
    rng = np.random.default_rng(0)
    arr = rng.random((50, 2)) * 100
    inv = rng.random((50, 2, 2)) * 50
    target = np.array([[40.0, 60.0], [30.0, 30.0]])
    out = model.split_arrivals(arr, inv, target)
    np.testing.assert_allclose(out.sum(axis=2), arr)
    assert (out >= 0).all()


def test_produce_respects_scarcest_component():
    inv = np.array([[[10.0], [100.0]]])        # 10 DRAM, 100 PMIC at one site
    demand = np.array([[[5.0]]])               # 5 units of one product
    bom = np.array([[4.0, 1.0]])               # needs 20 DRAM, 5 PMIC
    frac, use = model.produce(inv, demand, bom)
    assert frac[0, 0] == pytest.approx(0.5)
    np.testing.assert_allclose(use[0, :, 0], [10.0, 2.5])
    assert (use <= inv + 1e-12).all()


def test_confirm_order_caps():
    req = np.array([0.0, 50.0, 500.0])
    out = model.confirm_order(req, base=np.array(100.0), fill=np.array(0.5), inflation_cap=1.3)
    np.testing.assert_allclose(out, [0.0, 25.0, 65.0])


def test_sample_discrete_frequencies():
    dist = {8: 0.2, 9: 0.3, 10: 0.5}
    u = np.random.default_rng(1).random(200_000)
    x = model.sample_discrete(u, dist)
    for v, pr in dist.items():
        assert (x == v).mean() == pytest.approx(pr, abs=0.005)


def test_recommend_rule():
    s = pd.DataFrame({"fill_rate": [0.99, 0.96, 0.90], "total_cost": [10.0, 9.0, 5.0]}, index=list("xyz"))
    assert simulation.recommend(s) == ("y", True)
    s2 = s.assign(fill_rate=[0.5, 0.6, 0.7])
    assert simulation.recommend(s2) == ("z", False)


def test_precomputed_results_are_current():
    meta = json.loads((OUT / "meta.json").read_text())
    assert meta["params_fingerprint"] == params_fingerprint(data.Params()), \
        "assumptions changed: rerun `python scripts/precompute.py`"
    summary = pd.read_csv(OUT / "summary.csv", index_col="key")
    assert set(summary.index) == {s.key for s in data.STRATEGIES}
