# Memory Shortage Playbook

A Streamlit decision tool for a mid-size electronics OEM that has lost memory-chip allocation to AI data centers. It helps decide how to **source, stock and ship** components at the lowest total cost while keeping production running.

> ⚠️ **"Aster Networks" is a fictional company.** Its demand, costs, suppliers, lanes and carrier bids are invented. Market anchors are public data with links in [SOURCES.md](SOURCES.md):
> - memory spot and contract prices, lead times and allocation fill rates;
> - FRED producer price indexes;
> - DAT truckload rates.
>
> Results show what this model does under stated assumptions. They are not a forecast for any real firm.

## The problem

AI servers are absorbing conventional DRAM supply:
- Tier-1 memory lead times have reached **52 weeks** ([Sourceability, Oct-2026](https://sourceability.com/post/q3-2026-lead-time-report-highlights)).
- DRAM is **"under strict allocation"** ([VersaLogic](https://www.versalogic.com/blog/supply-chain-brief-memory-market-conditions-in-2026/)).
- Smaller OEMs reportedly receive **35–40%** of what they order, against about 70% for hyperscalers (DigiTimes via [Tom's Hardware](https://www.tomshardware.com/pc-components/storage/server-dram-prices-surge-50-percent), late 2025).
- DDR4 16Gb spot is **$82.72** ([TrendForce, 2026-11-03](https://www.trendforce.com/price/dram/dram_spot)).
- Q4-2026 contract prices are forecast at **+10–15% QoQ**.

A networking OEM in this position faces line-down risk for most of the next year.

## Approach

| Module | What it does |
|---|---|
| `shortage_lab/data.py` | Sourced market anchors (tagged S1–S10), the hypothetical company, all parameters, and the six strategies |
| `shortage_lab/model.py` | One-month inventory mechanics: receive and split across sites, build-to-scarcest-component, allocation confirmation, base-stock ordering |
| `shortage_lab/simulation.py` | Vectorised Monte Carlo: 10,000 paths × 24 months, seed 2026, **common random numbers** across strategies |
| `shortage_lab/optimization.py` | Carrier-award integer program (PuLP/CBC) with capacity, on-time, diversification and urgent-air constraints, plus a lead-time-slip sweep |
| `shortage_lab/robustness.py` | 500 random assumption sets (17 inputs redrawn) plus a one-lever-at-a-time ablation |
| `scripts/precompute.py` | Runs the simulation, optimizer and robustness check, and writes the outputs to `precomputed/` |
| `shortage_lab/warehouse.py` | Builds the 15 RAW tables (cleaned market data plus simulation outputs), reads marts from Snowflake or the local snapshot, and checks the mart contract |
| `scripts/load_snowflake.py` | Loads RAW tables into Snowflake (`write_pandas`, key-pair auth) and can run `dbt build` against Snowflake |
| `dbt/` | dbt project: 15 staging views → 9 mart tables, plus 39 data tests |
| `scripts/build_local_marts.py` | Runs the same dbt models on a local DuckDB file and exports the marts to `precomputed/marts/`, the app's offline fallback |
| `app.py` | Six tabs: S&OP summary, Network & assumptions, Strategy simulation, Freight procurement, Robustness, Market data & sources |

## Tech stack and data flow

**Python** (pandas, NumPy, SciPy, PuLP) · **Snowflake** (warehouse) · **dbt** (transformations and tests) · **Streamlit + Plotly** (app) · **pytest**. DuckDB serves only as dbt's local target, so the warehouse can be built and tested without a cloud account.

```
public market data (FRED, TrendForce, DAT…) ─┐
simulation + optimizer outputs (precomputed/) ┴─► RAW (15 tables)
        ─► dbt staging (15 views: typed, renamed)
        ─► dbt marts (9 tables) ─► Streamlit app
             Snowflake MEMORY_SHORTAGE.MARTS      (when the app has Snowflake secrets)
             precomputed/marts/*.csv snapshot     (fallback: same dbt SQL run on DuckDB)
```

| Mart | Grain | Used for |
|---|---|---|
| `mart_strategy_results` | strategy | KPI cards, strategy table, cost-vs-service chart. **The decision rule runs in SQL** (`is_recommended`), and a dbt test checks it against the Python rule. |
| `mart_strategy_monthly` | strategy × month | Fill-rate and DRAM-cover charts |
| `mart_strategy_ablation` | variant | Lever-by-lever cost impact |
| `mart_freight_award` | scenario × lane × carrier | Award table: loads, share of lane, cost |
| `mart_freight_lanes` | scenario × lane | Urgent, air and late loads, on-time rate |
| `mart_freight_scenarios` | slip scenario | Optimized vs incumbent spend and savings |
| `mart_robustness_scenarios` | assumption set | Win/tie/lose scatter and winner counts |
| `mart_robustness_summary` | outcome | Win/tie/lose rates and average inputs by outcome |
| `mart_market_ppi` | series × month | FRED PPIs rebased to Jan-2020 = 100, with year-over-year change |

dbt tests cover keys, accepted values and relationships, plus singular tests that re-check the model's math in SQL:
- exactly one strategy is recommended, and it matches the Python result;
- the total-cost identity holds;
- rates fall between 0 and 1;
- every lane's loads are fully awarded;
- on-time, urgent-air, diversification and capacity constraints hold in every scenario;
- robustness shares sum to 1.

**Live what-if runs** (sidebar sliders) still compute in Python. The marts hold the base case.

**Network**
- Suppliers: A (tier-1, allocation-only), A under a long-term allocation agreement (LTA), B (second-tier), C (broker).
- 2 warehouses (Reno, Dallas) and 2 plants (San Jose, Austin).
- 3 products using DDR4 16Gb DRAM and PMICs.

**Decision rule, fixed before viewing results:** lowest expected total cost among strategies with mean fill rate ≥ 95%. Total cost = landed component cost + holding cost + lost contribution margin − ending-stock value.

## Key findings (base case, 10,000 paths)

| Strategy | Fill rate | Stockout prob. (site-month) | P(any line-down month) | Landed cost | Holding | Lost revenue | Total cost, mean (P5–P95) |
|---|---|---|---|---|---|---|---|
| (a) Status quo single-source | 73.1% | 55.6% | 100% | $49.9M | $0.70M | $120.9M | $105.4M (91.5–119.8) |
| (b) Buy-ahead | 85.2% | 31.2% | 100% | $62.2M | $1.12M | $66.6M | $92.9M (79.1–107.2) |
| (c) Dual-sourcing | 86.6% | 38.8% | 100% | $63.5M | $0.73M | $60.5M | $91.1M (76.1–107.2) |
| (d) Higher safety stock | 73.1% | 55.6% | 100% | $50.2M | $0.76M | $120.9M | $105.3M (91.5–119.8) |
| (e) Allocation contract (LTA) | 89.3% | 24.5% | 100% | $76.8M | $2.32M | $48.0M | $93.2M (80.4–106.5) |
| **(f) Combined hedge** | **98.3%** | **6.6%** | **57%** | $86.0M | $2.45M | $7.6M | **$83.1M (71.8–96.1)** |

All values are over the 24-month horizon. Baseline revenue for the period is about $448M.

1. **Only the combined hedge meets 95% service**, and it is also the cheapest on total cost: $22.2M (21%) below the status quo. It spends $36.1M more on components to avoid $113M of lost revenue.
2. **Safety stock alone does nothing under allocation.** (d) performs the same as (a) because stock can't be built from parts that are never confirmed. A test confirms that safety stock *does* matter once supply is unconstrained.
3. **The levers inside (f), by expected cost added when each is removed:**
   - LTA: +$5.8M
   - supplier B: +$5.2M
   - buy-ahead: +$3.2M
   - broker spot-buy trigger: +$0.15M

   The 2-month safety stock in (f) **doesn't pay**: a 1-month version is $0.27M cheaper for 0.2 pts less fill.
4. **The near-term gap can't be fully closed.** Even (f) has a 57% chance of at least one site-month below 80% of demand. A's 8–12-month lead time means new contracts don't deliver until mid-to-late 2027.
5. **Freight:** the optimized award costs 11.1% less than the incumbent routing guide with lead times on plan ($513k vs $577k per month). It costs 17.0% less under a 5-day slip, when 18 of 197 monthly loads must fly. Past about 5 days, air can no longer recover loads, and late loads rise from 22 to 47. *The savings size depends on the hypothetical bid spreads.*
6. **Robustness:** across 500 random assumption sets, (f) **wins 91.2%, ties 1.0% and loses 7.8%**. In the 401 sets where any plan reaches 95% service, it wins 364 (90.8%). Losses cluster where supplier A confirms more (mean fill 63% vs 53% in wins) and the existing pipeline is healthier. In those cases dual-sourcing or buy-ahead alone is cheaper.

See [METHODOLOGY.md](METHODOLOGY.md) for assumptions and limitations.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt     # app + dbt (Snowflake and DuckDB adapters)
streamlit run app.py                    # reads the committed mart snapshot; no account needed
pytest                                  # 35 tests (see below)
```

To regenerate everything after changing an assumption in `shortage_lab/data.py`:

```bash
python scripts/precompute.py            # ~90 s: simulation, optimizer, robustness -> precomputed/
python scripts/build_local_marts.py     # RAW -> dbt build on DuckDB (24 models, 39 tests) -> precomputed/marts/
python scripts/load_snowflake.py --run-dbt   # optional: refresh Snowflake too
```

A test and an in-app banner flag stale precomputed files. Another test rebuilds every dbt model from RAW in a temporary DuckDB file and fails if the committed mart snapshot differs.

**What the 35 tests cover:**
- inventory balance and seed reproducibility;
- price-path drift, allocation caps and rationing;
- optimizer constraints, including a brute-force check;
- app smoke tests;
- marts reproducing the simulation outputs;
- the snapshot matching a fresh dbt build;
- the Snowflake reader, tested with a fake connection;
- the app falling back to the local snapshot when Snowflake is unreachable.

## Snowflake + dbt setup

You only need this to serve the marts from Snowflake. The app works without it.

**1. Create a trial account.** Sign up at <https://signup.snowflake.com> (30-day trial). Standard edition and any AWS US region are fine. In Snowsight, open the account menu (bottom left) → **Connect a tool to Snowflake** and copy the **account identifier** (`ORGNAME-ACCOUNTNAME`).

**2. Generate two key pairs**, one for loading and dbt and one for the read-only app. Snowflake is retiring password-only sign-in, and service users authenticate with keys.

```bash
mkdir -p keys && cd keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out shortage_dbt_key.p8 -nocrypt
openssl rsa -in shortage_dbt_key.p8 -pubout -out shortage_dbt_key.pub
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out shortage_app_key.p8 -nocrypt
openssl rsa -in shortage_app_key.p8 -pubout -out shortage_app_key.pub
cd ..
```

`*.p8` and `*.pem` files are git-ignored. Never commit them.

**3. Run the setup SQL.** Open [`warehouse/snowflake_setup.sql`](warehouse/snowflake_setup.sql) in a Snowsight worksheet and paste in each public key: the text between the `BEGIN`/`END` lines of the `.pub` file, joined into one line. Then **Run All** as ACCOUNTADMIN. The script creates:
- an XS warehouse that auto-suspends after 60 s, with a 10-credit monthly resource monitor;
- the `MEMORY_SHORTAGE` database with `RAW`, `STAGING` and `MARTS` schemas;
- two roles: `SHORTAGE_TRANSFORMER` (load and dbt) and `SHORTAGE_READER` (select on MARTS only);
- two service users, `SHORTAGE_DBT` and `SHORTAGE_APP`.

**4. Load RAW and build the marts in Snowflake:**

```bash
export SNOWFLAKE_ACCOUNT=ORGNAME-ACCOUNTNAME
export SNOWFLAKE_USER=SHORTAGE_DBT
export SNOWFLAKE_PRIVATE_KEY_PATH=$PWD/keys/shortage_dbt_key.p8
python scripts/load_snowflake.py --run-dbt
```

You should see 15 RAW tables loaded, then `dbt build` finishing with `PASS=63`. To iterate on dbt alone:

```bash
cd dbt && DBT_TARGET=snowflake dbt build --profiles-dir .
```

`dbt/profiles.yml` holds no secrets. Every credential comes from environment variables, and the default target is the local DuckDB file.

**5. Point the app at Snowflake.** Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (git-ignored), fill in the account identifier, and paste the contents of `keys/shortage_app_key.p8` into `private_key`. Run `streamlit run app.py`; the sidebar should say **Data source: Snowflake · MEMORY_SHORTAGE.MARTS**.

**How the fallback works:**
- **No secrets, or `MARTS_SOURCE=local`:** the app reads `precomputed/marts/` and never touches Snowflake.
- **Login timeout (10 s), auth error, or marts missing columns the app needs:** the app falls back to the snapshot and says so in the sidebar.
- **Snowflake reads succeed:** results are cached for an hour, so only the first visitor waits for the warehouse to resume.

## Deploy to Streamlit Community Cloud

1. Push this folder to a **public GitHub repo**, with `precomputed/` (including `precomputed/marts/`) included.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click **Create app → Deploy a public app from GitHub**.
3. Choose the repo, branch `main`, and main file `app.py`.
4. Under **Advanced settings**, choose **Python 3.12** or newer (tested on 3.13).
5. Optional, to serve from Snowflake: under **Advanced settings → Secrets**, paste the contents of your filled-in `secrets.toml` (the read-only `SHORTAGE_APP` user). Without secrets, the app serves the local mart snapshot.
6. Click **Deploy**.

Streamlit Cloud installs `requirements.txt` (runtime only; dbt and DuckDB are in `requirements-dev.txt`). PuLP 2.9 bundles the CBC solver for Linux, so no system packages are needed.
