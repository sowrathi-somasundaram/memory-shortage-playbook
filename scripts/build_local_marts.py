"""Build the warehouse locally with no cloud account: RAW tables -> DuckDB -> dbt build
(staging + marts + tests, same SQL as Snowflake) -> export marts to precomputed/marts/.

The exported CSVs are the Streamlit app's offline fallback.

    python scripts/build_local_marts.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shortage_lab import warehouse  # noqa: E402

DB_PATH = ROOT / "warehouse" / "local.duckdb"
DBT_DIR = ROOT / "dbt"

def load_raw(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("create schema if not exists raw")
    for name, df in warehouse.build_raw_tables().items():
        con.register("df_view", df)
        con.execute(f"create or replace table raw.{name} as select * from df_view")
        con.unregister("df_view")
        print(f"  raw.{name}: {len(df):,} rows")


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        load_raw(con)
    env = {**os.environ, "DBT_TARGET": "local", "DBT_DUCKDB_PATH": str(DB_PATH)}
    dbt = Path(sys.executable).with_name("dbt")
    cmd = [str(dbt) if dbt.exists() else "dbt", "build", "--project-dir", str(DBT_DIR),
           "--profiles-dir", str(DBT_DIR), "--target", "local"]
    subprocess.run(cmd, check=True, env=env)
    warehouse.MARTS_DIR.mkdir(exist_ok=True)
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        for name in warehouse.MARTS:
            df = con.execute(f"select * from marts.{name}").df().sort_values(warehouse.MART_KEYS[name])
            df.to_csv(warehouse.MARTS_DIR / f"{name}.csv", index=False)
            print(f"  exported {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
