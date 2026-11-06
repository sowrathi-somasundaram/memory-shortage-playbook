"""Warehouse I/O: raw tables for Snowflake (and the local DuckDB build), and mart readers.

Flow:  precomputed/*.csv + data/fred + data.py  ->  RAW tables  ->  dbt staging views
       ->  dbt mart tables  ->  app.  The same dbt models run on Snowflake (prod) and on
       DuckDB (local), and the DuckDB marts are exported to precomputed/marts/ as the app's
       offline fallback, so both paths serve identical numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import data, optimization, robustness
from .cache import OUT

MARTS_DIR = OUT / "marts"
SNOWFLAKE_RAW_SCHEMA = "RAW"
SNOWFLAKE_MARTS_SCHEMA = "MARTS"

# Mart tables the app reads (built by dbt/models/marts) and each one's unique key, used to
# give exported snapshots a deterministic row order.
MART_KEYS = {
    "mart_strategy_results": ["strategy_key"],
    "mart_strategy_monthly": ["strategy_key", "month_number"],
    "mart_strategy_ablation": ["variant"],
    "mart_freight_award": ["mean_slip_days", "lane", "carrier"],
    "mart_freight_lanes": ["mean_slip_days", "lane"],
    "mart_freight_scenarios": ["mean_slip_days"],
    "mart_robustness_scenarios": ["scenario_id"],
    "mart_robustness_summary": ["outcome"],
    "mart_market_ppi": ["series_id", "observation_date"],
}
MARTS = list(MART_KEYS)


def _snake(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=lambda c: c.strip().lower().replace(" ", "_"))


def build_raw_tables() -> dict[str, pd.DataFrame]:
    """Cleaned market data and simulation outputs, one DataFrame per RAW table."""
    fred = []
    for sid, label in data.FRED_SERIES.items():
        s = data.load_fred(sid).dropna()
        fred.append(pd.DataFrame({"series_id": sid, "series_label": label,
                                  "observation_date": s.index.date, "index_value": s.values}))
    anchors = pd.DataFrame([{"anchor_id": k, "value": a.value, "unit": a.unit, "source_id": a.source,
                             "note": a.note} for k, a in data.MARKET_ANCHORS.items()])
    strategies = pd.DataFrame([{
        "strategy_key": s.key, "strategy_name": s.name, "description": s.description,
        "supplier_shares": json.dumps(s.shares), "ss_months": s.ss_months,
        "buy_ahead_months": s.buy_ahead_months, "emergency_spot": s.emergency_spot,
    } for s in data.STRATEGIES])
    meta = json.loads((OUT / "meta.json").read_text())
    slip = pd.DataFrame({"scenario": list(optimization.SLIP_SCENARIOS),
                         "mean_slip_days": list(optimization.SLIP_SCENARIOS.values())})
    tables = {
        "raw_fred_ppi": pd.concat(fred, ignore_index=True),
        "raw_market_anchors": anchors,
        "raw_strategies": strategies,
        "raw_strategy_summary": pd.read_csv(OUT / "summary.csv").rename(columns={"key": "strategy_key"}),
        "raw_strategy_monthly": pd.read_csv(OUT / "monthly.csv").rename(columns={"key": "strategy_key"}),
        "raw_strategy_samples": pd.read_csv(OUT / "samples.csv").rename(columns={"key": "strategy_key"}),
        "raw_ablation": pd.read_csv(OUT / "ablation.csv"),
        "raw_lanes": data.LANES.copy(),
        "raw_carrier_bids": data.carrier_bids(),
        "raw_slip_scenarios": slip,
        "raw_freight_awards": pd.read_csv(OUT / "freight_awards.csv"),
        "raw_freight_lanes": pd.read_csv(OUT / "freight_lanes.csv"),
        "raw_freight_sweep": pd.read_csv(OUT / "freight_sweep.csv"),
        "raw_robustness": pd.read_csv(OUT / "robustness.csv"),
        "raw_run_meta": pd.DataFrame([{**meta, "service_target": data.SERVICE_TARGET,
                                       "tie_tolerance": robustness.TIE_TOL,
                                       "on_time_target": data.ON_TIME_TARGET,
                                       "max_lane_share": data.MAX_LANE_SHARE}]),
    }
    return {name: _snake(df) for name, df in tables.items()}


def read_local_marts(directory: Path = MARTS_DIR) -> dict[str, pd.DataFrame]:
    """Offline fallback: mart snapshots exported from the local dbt (DuckDB) build."""
    out = {}
    for name in MARTS:
        df = pd.read_csv(directory / f"{name}.csv")
        for col in df.columns:
            if col.endswith("_date"):
                df[col] = pd.to_datetime(df[col])
        out[name] = df
    return out


def read_snowflake_marts(conn, schema: str = SNOWFLAKE_MARTS_SCHEMA) -> dict[str, pd.DataFrame]:
    """Read every mart over an open snowflake.connector connection (column names lower-cased)."""
    out = {}
    cur = conn.cursor()
    try:
        for name in MARTS:
            cur.execute(f"select * from {schema}.{name}")
            df = cur.fetch_pandas_all() if hasattr(cur, "fetch_pandas_all") else pd.DataFrame(
                cur.fetchall(), columns=[c[0] for c in cur.description])
            df.columns = [c.lower() for c in df.columns]
            for col in df.columns:
                if col.endswith("_date"):
                    df[col] = pd.to_datetime(df[col])
            out[name] = df
    finally:
        cur.close()
    return out


def check_mart_contract(marts: dict[str, pd.DataFrame], reference: dict[str, pd.DataFrame]) -> list[str]:
    """Columns the app relies on must match the local snapshot; returns problems (empty = OK)."""
    problems = []
    for name in MARTS:
        if name not in marts:
            problems.append(f"missing {name}")
        elif set(reference[name].columns) - set(marts[name].columns):
            problems.append(f"{name} lacks {sorted(set(reference[name].columns) - set(marts[name].columns))}")
    return problems


def connect_snowflake(cfg: dict):
    """Open a Snowflake connection with key-pair auth.

    ``cfg`` keys: account, user, role, warehouse, database, and either private_key_path
    (a .p8 file) or private_key (the PEM text, e.g. from Streamlit secrets); optional
    private_key_passphrase. Password logins are not used: Snowflake is phasing out
    single-factor passwords, and service users must use keys.
    """
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    pem = cfg.get("private_key")
    if not pem:
        pem = Path(cfg["private_key_path"]).expanduser().read_text()
    passphrase = cfg.get("private_key_passphrase")
    key = serialization.load_pem_private_key(pem.encode(), password=passphrase.encode() if passphrase else None)
    der = key.private_bytes(encoding=serialization.Encoding.DER,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption())
    return snowflake.connector.connect(
        account=cfg["account"], user=cfg["user"], private_key=der,
        role=cfg.get("role"), warehouse=cfg.get("warehouse"), database=cfg.get("database"),
        login_timeout=int(cfg.get("login_timeout", 15)), request_timeout=int(cfg.get("request_timeout", 30)),
        enable_server_session_keep_alive_auto_detection=False,
        application="memory_shortage_playbook",
    )


def snowflake_config_from_env() -> dict:
    import os
    return {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "private_key_path": os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        "private_key_passphrase": os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
        "role": os.environ.get("SNOWFLAKE_ROLE", "SHORTAGE_TRANSFORMER"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "SHORTAGE_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "MEMORY_SHORTAGE"),
    }
