# Methodology, assumptions and limitations

> **The company is fictional.** "Aster Networks" and all of its demand, costs, suppliers,
> lanes and carrier bids are invented. Market anchors are public data (SOURCES.md). The
> results describe how this model behaves under these assumptions. They are not a forecast
> for any real firm.

## 1. Network and products

| Element | Setup |
|---|---|
| Products | SW-48 switch, AP-7 access point and ER-4 router. Each uses DDR4 16Gb DRAM packages and PMICs (BOM in `data.PRODUCTS`). |
| Sites | **West**: Reno WH → San Jose plant. **East**: Dallas WH → Austin plant. Component stock is held per site. |
| Demand | 2,700–9,000 units/month per product, about $18.7M revenue/month. Baseline need is 42,400 DRAM packages and 47,800 PMICs per month. |
| Suppliers | **A**: tier-1, allocation-only, cheapest. **A under LTA**: same supplier with protected allocation, +15% price and 90% take-or-pay. **B**: second-tier, +10% price, shorter lead time. **C**: broker or spot market, at spot × 1.10, 1–2 month lead time, capped at 30% of monthly need, 3% rejects. |
| Horizon | 24 monthly periods (Nov-2026 to Oct-2028), with monthly review. |

## 2. Inventory model (`shortage_lab/model.py`, `simulation.py`)

Each month, for every simulated path:

1. **Receive.** Deliveries due this month arrive. They are split across the two sites in proportion to each site's shortfall against its target stock.
2. **Build.** Demand is realised. Each site builds as many units as its scarcest component allows. Shortages are rationed proportionally across products. Unbuilt demand is **lost, not backlogged.**
3. **Hold.** Holding cost is 25%/yr ÷ 12 on month-end stock, valued at the current contract price.
4. **Order.** A base-stock policy sets the order:
   - Order-up-to level = (share-weighted mean lead time + 1 + safety-stock months) × mean monthly need.
   - The required quantity is split across suppliers by strategy share.
   - Each supplier confirms only `fill × min(request, 1.3 × allocation base)`. The allocation base is that supplier's share of baseline need. Over-ordering therefore wins at most 30% extra.
   - Confirmed quantities arrive after a sampled lead time. Their cost is locked at the order-month price, plus 2% freight (6% for expedited broker air).

**Starting position (same for all strategies).** Each site holds 2 months of on-hand stock. Supplier A has an in-transit pipeline from past orders, set to the steady-state flow at the reduced historic allocation: 60% of DRAM need and 85% of PMIC need, tapered by the lead-time distribution. Decisions made today cannot change deliveries already in that pipeline. This is the realistic "lost allocation" starting point.

**Total relevant cost (the objective)**
= landed purchase cost of units received in the horizon
+ holding cost
+ lost contribution margin (price − non-memory variable cost) on unbuilt units
− value of ending stock at the final contract price.

Lost revenue is reported separately. It is not added to cost, because that would double-count the component spend that was avoided.

**Metrics** (each is a mean over 10,000 paths, with P5/P95 where shown):
- **Fill rate**: units built ÷ units demanded.
- **Stockout probability**: share of site-months where under 99.5% of demand was built.
- **P(line-down)**: probability of at least one site-month under 80% of demand.
- Landed cost, holding cost, lost revenue, ending stock value and total cost.

**Decision rule, fixed before results were viewed.** Recommend the strategy with the lowest expected total cost among those with mean fill rate ≥ 95%. If none qualifies, pick the lowest-cost strategy and flag it.

## 3. Random inputs (common random numbers, seed 2026)

All strategies are evaluated on **identical** random paths.

| Input | Distribution | Basis |
|---|---|---|
| Lead time, A DRAM | 8–12 months (mean 9.65 ≈ 42 weeks) | S3 (52 weeks), S4 (32–40+ weeks; 8–52 weeks) |
| Lead time, A PMIC | 4–9 months (mean 6.1) | S5 (16–40 weeks) |
| Lead time, B | DRAM 5–7 months, PMIC 3–5 months | HYP |
| Lead time, C (broker) | 1 month (85%) or 2 months (15%) | HYP |
| Allocation fill, A DRAM | Beta, mean 55%, concentration 25 | Between the 35–40% small-OEM and 70% hyperscaler figures in S6. **The mid-size placement is an assumption.** |
| Allocation fill, other suppliers | A PMIC 80%, B 80%/88%, LTA 92%/95%, broker 85%/90% | HYP |
| Allocation shock | 35% chance per path of a further cut from a random month onward: non-contract fills × 0.75, LTA × 0.95 | HYP |
| DRAM contract price | Lognormal random walk. Drift is +12.5%/quarter for 3 months, decaying 15%/month after that. Monthly volatility 5%. | Drift from S2 (TrendForce Q4 outlook); decay and volatility HYP |
| DRAM contract-to-spot ratio | Contract = 0.75 × spot ($82.72), i.e. $62.04/package | Spot from S1; ratio HYP |
| PMIC price | Drift (1.26)^(1/12) − 1 ≈ 1.9%/month; s.d. 2.05%/month | S7 (FRED PPI) |
| Demand | Lognormal with mean 1. AR(1) common factor (σ 8%, ρ 0.6) plus product×site noise (σ 12%). | HYP |

## 4. Strategies

| Key | Strategy | Definition |
|---|---|---|
| a | Status quo | 100% A; 1-month safety stock |
| b | Buy-ahead | (a) plus a forward purchase of 3 months of need from the broker at month-0 spot × 1.10. Delivered in tranches limited by broker capacity. |
| c | Dual-sourcing | 60% A, 40% B; 1-month safety stock |
| d | Higher safety stock | 100% A; 3-month safety stock |
| e | Allocation contract | 100% A under an LTA: +15% price, 90% take-or-pay, protected fill |
| f | Combined hedge | 70% LTA and 30% B; 2-month safety stock; 1-month buy-ahead; broker spot buys whenever next month's cover drops below 0.5 months |

(f) was specified **before** any results were viewed and has not been re-tuned since. The ablation shows a 1-month safety stock would be 0.3% cheaper. That result is reported, and (f) was left as specified.

## 5. Freight procurement (`shortage_lab/optimization.py`)

The model is an integer program (PuLP with the CBC solver). It minimises monthly freight cost plus penalties for unrecoverable or late loads, subject to:
- every lane's loads are fully awarded;
- carriers win only lanes they bid on, within lane capacity and total monthly capacity;
- volume-weighted on-time rate ≥ 93% on each lane;
- no truck carrier takes more than 70% of a lane with 10 or more loads;
- **urgent loads must fly.**

**Inputs**
- **Lanes:** 6 lanes (port → warehouse, warehouse → plant, and cross-country rebalancing), 197 loads/month, 20,000 lb each. All HYP.
- **Truck bids:** 0.90–1.12 × the DAT dry-van contract rate of $3.24/mile (S10) × approximate road miles, with a $650 minimum.
- **Air bids:** $0.85–0.95/lb plus a small distance factor. These are **HYP; there is no public domestic air-freight benchmark in this project.**

**Urgency model.** Upstream delay D ~ Gamma(shape 2, mean = slip scenario). For each lane with planning buffer B:
- a load is **urgent** if D + truck transit > B but D + air transit ≤ B;
- a load is **late even by air** if D + air transit > B.

Lanes from a warehouse to its local plant are buffered by warehouse stock and are not exposed to supplier slip. Late loads cost $25,000 each in *both* the optimized and benchmark plans, so the penalty never flatters the optimizer.

**Benchmark (hypothetical status quo).** The incumbent carrier T1 hauls every load, and urgent loads are bought as spot air (+30% over the air bid), subject to the same air capacity.

## 6. Robustness (`shortage_lab/robustness.py`)

The model draws 500 assumption sets uniformly from ranges around the base case, with 1,000 paths each and a fresh seed per set. The ranges include:
- A's DRAM fill from 37.5% to 70% (the full S6 range);
- LTA fill 80–97% and LTA premium 5–30%;
- DRAM contract price from −5% to +25% per quarter, and drift decay;
- contract/spot ratio, broker markup and broker capacity;
- lead-time shift of ±2 months;
- demand volatility × 0.5–1.5;
- holding rate 15–35%;
- shock probability 0–70%;
- starting pipeline 45–80%;
- margin × 0.7–1.3.

The same decision rule is applied in each set:
- **win**: the base-case recommendation is selected;
- **tie**: it is within 1% of the winner's expected cost and passes the same service test;
- **lose**: anything else.

An **ablation** removes one lever at a time from (f).

## 7. Limitations — what the model can't tell you

- **The company data is invented.** The absolute dollar figures (e.g. "$22M lower total cost") depend on hypothetical prices, margins and volumes. The *ranking* of strategies and the *mechanisms* are the transferable findings.
- **Allocation is the dominant input, and its public evidence is thin.** The 35–40% and 70% fill-rate figures are late-2025 secondary reporting (S6). Robustness shows the ranking flips toward cheaper plans when A confirms about 63% or more.
- **Lost sales, not backlog.** B2B networking customers often wait, which would make stockouts cheaper than modelled. That would favour leaner strategies.
- **No supplier or customer reaction.** Allocation is exogenous. In reality, LTAs, prepayments and relationships change a customer's allocation tier, and competitors bid for the same broker stock.
- **The LTA terms are assumptions.** Real LTAs may include price resets, prepayment and volume bands. The take-or-pay exposure modelled here is simplified to a fixed 90% commitment.
- **Broker quality risk is only a 3% reject rate.** Counterfeit risk, warranty exposure and qualification time for supplier B are not modelled. Qualifying a second source can take months, while the model assumes B is usable at month 0.
- **Rationing is proportional.** A real planner would prioritise high-margin SKUs, which would make every strategy look better.
- **No product redesign or substitution** (e.g. moving to DDR5, where spot is cheaper per S1).
- **Freight volumes are not linked to the Monte Carlo.** The freight module is a monthly snapshot, and its savings depend on the hypothetical bid spreads.
- **Pipeline orders that arrive after the horizon are excluded** from both cost and value for every strategy.
- **Monte Carlo error.** With 10,000 paths, the standard error of mean total cost is $0.08–0.10M per strategy. Because strategies share random paths, the standard error of the difference between (f) and any other strategy is only $0.03–0.06M, far below the $8M+ gaps reported. The robustness check uses 1,000 paths per set, so near-ties there are noisier.

## 8. Data pipeline (Snowflake + dbt)

**Model is unchanged.** The warehouse layer adds no new modelling. It stores and serves the outputs described above.

**Layers.** RAW holds:
- the cleaned market data: FRED snapshots and the sourced anchors;
- the hypothetical company inputs: lanes and carrier bids;
- the simulation, optimizer and robustness outputs.

dbt staging views type and rename these columns. dbt mart tables join, derive and aggregate them, for example deltas versus the status quo, share of lane, PPIs rebased to Jan-2020 = 100, and year-over-year change.

**The decision rule appears twice.** It is applied once in Python (`simulation.recommend`) and once in SQL (`mart_strategy_results.is_recommended`). A dbt test fails if the two disagree.

**One SQL codebase, two engines.** The same dbt models run on Snowflake and on DuckDB. A pytest rebuilds them on DuckDB and compares the result with the committed fallback snapshot. The SQL is written to be portable (ANSI casts, window functions, and dbt's `dateadd` macro).

**Limitation.** The Snowflake path (`scripts/load_snowflake.py`, the `snowflake` dbt target, and the app's Snowflake reader) was written against the Snowflake connector 5.2 and dbt-snowflake 1.12 APIs. It has been tested only with a fake connection, not against a live account. Run setup step 4 in the README and confirm `dbt build` reports `PASS=63` on your account.
