"""Precompute the baseline results the app shows on first load.

    python scripts/precompute.py            # full: 10,000 runs + 500 robustness scenarios
    python scripts/precompute.py --quick    # smaller robustness set for development
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shortage_lab import data, optimization, robustness, simulation  # noqa: E402
from shortage_lab.cache import OUT, params_fingerprint  # noqa: E402


def main(quick: bool) -> None:
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    params = data.Params()
    res = simulation.run_all(params, keep_paths=True)
    summary = simulation.summarize(res)
    rec, met = simulation.recommend(summary)
    summary.to_csv(OUT / "summary.csv")

    monthly = []
    for k, r in res.items():
        fill = r["paths"]["fill"]
        cover = r["paths"]["cover"]
        for t in range(params.horizon):
            monthly.append({"key": k, "month": t + 1, "fill_mean": fill[:, t].mean(),
                            "fill_p10": np.percentile(fill[:, t], 10),
                            "fill_p90": np.percentile(fill[:, t], 90),
                            "dram_cover_months": cover[:, t, 0].mean(),
                            "pmic_cover_months": cover[:, t, 1].mean()})
    pd.DataFrame(monthly).to_csv(OUT / "monthly.csv", index=False)

    rng = np.random.default_rng(0)
    idx = rng.choice(simulation.DEFAULT_RUNS, size=2000, replace=False)
    pd.DataFrame([{"key": k, "total_cost": r["total_cost"][i], "fill_rate": r["fill_rate"][i]}
                  for k, r in res.items() for i in idx]).to_csv(OUT / "samples.csv", index=False)
    print(f"baseline done in {time.time() - t0:.1f}s; recommended={rec} (target met: {met})")

    robustness.ablation(params).to_csv(OUT / "ablation.csv", index=False)
    print(f"ablation done in {time.time() - t0:.1f}s")

    sweep = optimization.slip_sweep()
    sweep.to_csv(OUT / "freight_sweep.csv", index=False)
    awards, lanes = [], []
    for name, slip in optimization.SLIP_SCENARIOS.items():
        res = optimization.solve_award(slip)
        awards.append(res.award.assign(scenario=name))
        lanes.append(res.lane_summary.assign(scenario=name))
    pd.concat(awards).to_csv(OUT / "freight_awards.csv", index=False)
    pd.concat(lanes).to_csv(OUT / "freight_lanes.csv", index=False)

    n = 60 if quick else 500
    rob = robustness.robustness(rec, n_scenarios=n, runs=1000)
    rob.to_csv(OUT / "robustness.csv", index=False)
    print(f"robustness done in {time.time() - t0:.1f}s")

    meta = {"runs": simulation.DEFAULT_RUNS, "seed": simulation.DEFAULT_SEED,
            "recommended": rec, "target_met": bool(met), "robustness_scenarios": n,
            "robustness_runs_per_scenario": 1000, "params_fingerprint": params_fingerprint(params),
            "generated": time.strftime("%Y-%m-%d %H:%M")}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
