"""Load the RAW tables into Snowflake, then (optionally) run dbt against Snowflake.

Needs the env vars described in README "Snowflake + dbt setup" (key-pair auth):
SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY_PATH, and optionally
SNOWFLAKE_ROLE / SNOWFLAKE_WAREHOUSE / SNOWFLAKE_DATABASE / SNOWFLAKE_PRIVATE_KEY_PASSPHRASE.

    python scripts/load_snowflake.py             # load RAW only
    python scripts/load_snowflake.py --run-dbt   # load RAW, then dbt build on Snowflake
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snowflake.connector.pandas_tools import write_pandas  # noqa: E402

from shortage_lab import warehouse  # noqa: E402


def main(run_dbt: bool) -> None:
    cfg = warehouse.snowflake_config_from_env()
    conn = warehouse.connect_snowflake(cfg)
    try:
        conn.cursor().execute(f"use schema {cfg['database']}.{warehouse.SNOWFLAKE_RAW_SCHEMA}")
        for name, df in warehouse.build_raw_tables().items():
            ok, _, nrows, _ = write_pandas(conn, df, table_name=name.upper(), auto_create_table=True,
                                           overwrite=True, quote_identifiers=False, use_logical_type=True)
            print(f"  {warehouse.SNOWFLAKE_RAW_SCHEMA}.{name.upper()}: {nrows:,} rows {'ok' if ok else 'FAILED'}")
    finally:
        conn.close()
    if run_dbt:
        dbt = Path(sys.executable).with_name("dbt")
        subprocess.run([str(dbt) if dbt.exists() else "dbt", "build", "--project-dir", str(ROOT / "dbt"),
                        "--profiles-dir", str(ROOT / "dbt"), "--target", "snowflake"],
                       check=True, env={**os.environ, "DBT_TARGET": "snowflake"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dbt", action="store_true")
    main(ap.parse_args().run_dbt)
