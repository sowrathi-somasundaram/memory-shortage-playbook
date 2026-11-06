import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shortage_lab import simulation, warehouse
from shortage_lab.cache import OUT

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def marts():
    return warehouse.read_local_marts()


def test_raw_tables_are_clean():
    tables = warehouse.build_raw_tables()
    assert len(tables) == 15
    for name, df in tables.items():
        assert len(df), name
        assert all(c == c.lower() and " " not in c for c in df.columns), name
    assert tables["raw_fred_ppi"]["index_value"].notna().all()
    assert not tables["raw_strategy_summary"].duplicated("strategy_key").any()


def test_strategy_mart_reproduces_simulation_results(marts):
    mart = marts["mart_strategy_results"].set_index("strategy_key").sort_index()
    summary = pd.read_csv(OUT / "summary.csv", index_col="key").sort_index()
    for col in ["fill_rate", "stockout_prob", "landed_cost", "holding_cost", "lost_revenue", "total_cost"]:
        np.testing.assert_allclose(mart[col], summary[col], rtol=1e-12)
    np.testing.assert_allclose(mart["p_line_down"], summary["line_down"], rtol=1e-12)
    rec, met = simulation.recommend(summary)
    assert mart.index[mart["is_recommended"]].tolist() == [rec]
    assert bool(mart.loc[rec, "meets_service_target"]) == met


def test_freight_and_robustness_marts_match_outputs(marts):
    sweep = pd.read_csv(OUT / "freight_sweep.csv").sort_values("mean_slip_days")
    fs = marts["mart_freight_scenarios"].sort_values("mean_slip_days")
    np.testing.assert_allclose(fs["optimized_freight"], sweep["optimized_freight"])
    award = marts["mart_freight_award"]
    vols = award.groupby(["scenario", "lane"])["loads"].sum()
    assert (vols.values == award.groupby(["scenario", "lane"])["lane_loads_per_month"].first().values).all()
    rob = pd.read_csv(OUT / "robustness.csv")
    summ = marts["mart_robustness_summary"].set_index("outcome")
    assert summ["n_sets"].to_dict() == rob["outcome"].value_counts().to_dict()
    assert summ["share_of_sets"].sum() == pytest.approx(1.0)


@pytest.mark.skipif(shutil.which("dbt") is None and not Path(sys.executable).with_name("dbt").exists(),
                    reason="dbt not installed (pip install -r requirements-dev.txt)")
def test_committed_mart_snapshot_equals_fresh_dbt_build(tmp_path):
    """Rebuild every model from RAW on DuckDB in a temp dir; the result must match the
    committed precomputed/marts/ snapshot the app falls back to."""
    import duckdb

    db = tmp_path / "check.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create schema raw")
        for name, df in warehouse.build_raw_tables().items():
            con.register("v", df)
            con.execute(f"create table raw.{name} as select * from v")
            con.unregister("v")
    dbt = Path(sys.executable).with_name("dbt")
    subprocess.run([str(dbt) if dbt.exists() else "dbt", "build", "--project-dir", str(ROOT / "dbt"),
                    "--profiles-dir", str(ROOT / "dbt"), "--target", "local",
                    "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
                   check=True, capture_output=True,
                   env={**os.environ, "DBT_TARGET": "local", "DBT_DUCKDB_PATH": str(db)})
    snapshot = warehouse.read_local_marts()
    with duckdb.connect(str(db), read_only=True) as con:
        for name in warehouse.MARTS:
            fresh = con.execute(f"select * from marts.{name}").df()
            snap = snapshot[name]
            assert list(fresh.columns) == list(snap.columns), name
            assert len(fresh) == len(snap), name
            num = fresh.select_dtypes("number").columns
            key = warehouse.MART_KEYS[name]
            f = fresh.sort_values(key).reset_index(drop=True)
            s = snap.sort_values(key).reset_index(drop=True)
            np.testing.assert_allclose(f[num].astype(float), s[num].astype(float), rtol=1e-9, err_msg=name)


class _FakeCursor:
    def __init__(self, frames):
        self.frames, self.current = frames, None

    def execute(self, sql):
        self.current = sql.split(".")[-1].strip()

    def fetch_pandas_all(self):
        return self.frames[self.current].rename(columns=str.upper)

    def close(self):
        pass


class _FakeConn:
    def __init__(self, frames):
        self.frames = frames

    def cursor(self):
        return _FakeCursor(self.frames)


def test_snowflake_reader_normalises_columns(marts):
    as_text = {k: v.astype({c: str for c in v.columns if c.endswith("_date")}) for k, v in marts.items()}
    remote = warehouse.read_snowflake_marts(_FakeConn(as_text))
    assert warehouse.check_mart_contract(remote, marts) == []
    assert pd.api.types.is_datetime64_any_dtype(remote["mart_market_ppi"]["observation_date"])


def test_contract_check_flags_missing_columns(marts):
    broken = dict(marts)
    broken["mart_strategy_results"] = marts["mart_strategy_results"].drop(columns=["is_recommended"])
    del broken["mart_market_ppi"]
    problems = warehouse.check_mart_contract(broken, marts)
    assert any("is_recommended" in p for p in problems) and any("mart_market_ppi" in p for p in problems)


def test_app_falls_back_to_local_marts_when_snowflake_unreachable(monkeypatch):
    monkeypatch.delenv("MARTS_SOURCE", raising=False)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from streamlit.testing.v1 import AppTest

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.secrets["snowflake"] = {"account": "invalid-account-for-tests.invalid", "user": "NOBODY",
                               "private_key": pem, "login_timeout": 3, "request_timeout": 3}
    at.run()
    assert not at.exception
    captions = " ".join(c.value for c in at.sidebar.caption)
    assert "Local mart snapshot" in captions and "Snowflake unavailable" in captions


def test_meta_matches_marts(marts):
    meta = json.loads((OUT / "meta.json").read_text())
    assert marts["mart_strategy_results"]["runs"].iloc[0] == meta["runs"]
