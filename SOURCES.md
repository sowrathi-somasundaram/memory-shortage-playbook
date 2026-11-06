# Sources

All accessed **2026-11-03**. IDs (S1, S2, …) are referenced in `shortage_lab/data.py`
(`MARKET_ANCHORS`) and shown in the app's *Network & assumptions* tab.

**Verification** column:
- *Fetched*: I opened the page and read the figure there.
- *Secondary*: the figure is reported by the listed outlet, citing an original I could not open (paywalled or not found).

Treat secondary figures as less certain.

## Figures used in the model

| ID | Figure used | Value in model | Source | Verification |
|---|---|---|---|---|
| S1 | DDR4 16Gb (2Gx8) 3200 spot price, session average | $82.72 per package (DDR5 16Gb $61.50 shown for context) | TrendForce / DRAMeXchange, DRAM spot price page, snapshot 2026-11-03 18:10 GMT+8: <https://www.trendforce.com/price/dram/dram_spot> | Fetched |
| S2 | Q4-2026 conventional DRAM contract price outlook | +10–15% QoQ, midpoint 12.5% used for the near-term drift | TrendForce September 2026 forecast, as reported in Sourceability's Q3-2026 Lead Time Report highlights: <https://sourceability.com/post/q3-2026-lead-time-report-highlights>. Related: TrendForce DRAM Market Bulletin, Sep 23 2026 (paywalled): <https://trendforce.com/research/download/RP260923EN>; IT之家 / ifeng summary (Sep 30 2026, 10–15% excl. HBM, 15–20% incl. HBM): <https://tech.ifeng.com/c/8wqosax55jy> | Fetched (Sourceability); TrendForce original paywalled |
| S3 | Tier-1 memory lead time and allocation | Micron lead times on several technologies at 52 weeks; DDR4/LPDDR5/some DDR5 "on allocation almost across the board" | Sourceability, *Q3 2026 Lead Time Report Highlights*, Oct 15 2026: <https://sourceability.com/post/q3-2026-lead-time-report-highlights> | Fetched |
| S4 | Memory lead-time range and allocation behaviour | 32–40+ weeks (Jan 2026); "8 to 52 weeks depending on the product" (Aug 2026); "All DRAM categories are under strict allocation" (Apr 2026) | VersaLogic, *Supply Chain Brief: Memory Market Conditions in 2026* (rolling updates, latest Sep 14 2026): <https://www.versalogic.com/blog/supply-chain-brief-memory-market-conditions-in-2026/> | Fetched |
| S5 | PMIC lead time | 16–40 weeks expected in 2026 (12–26 in 2024) | Hubble Network, *Lead Times in 2026: How to Plan Your Hardware BOM for Reality* (undated, © 2026): <https://hubble.com/community/guides/lead-times-in-2026-how-to-plan-your-hardware-bom-for-reality/> | Fetched |
| S6 | Allocation fill rates | ~70% of ordered server DRAM for large U.S./Chinese hyperscalers; 35–40% for channel players and smaller OEMs. **Dated: late-2025 reporting on Q4-2025 contracts.** | DigiTimes, as reported by Tom's Hardware: <https://www.tomshardware.com/pc-components/storage/server-dram-prices-surge-50-percent> and TechSpot: <https://www.techspot.com/news/110045-ai-driven-demand-pushes-dram-prices-up-50.html> | Secondary (DigiTimes original not found) |
| S7 | Semiconductor & other electronic component PPI | +26.0% YoY (Sep-2026), monthly s.d. 2.05% over the last 36 months; drives PMIC price drift | FRED, series PCU33443344: <https://fred.stlouisfed.org/series/PCU33443344> (snapshot in `data/fred/`) | Fetched (CSV) |
| S8 | Long-distance truckload PPI | +17.9% YoY (Sep-2026); context for freight rates | FRED, series PCU484121484121: <https://fred.stlouisfed.org/series/PCU484121484121> | Fetched (CSV) |
| S9 | Scheduled air freight PPI | +5.8% YoY (Sep-2026); context | FRED, series PCU481112481112: <https://fred.stlouisfed.org/series/PCU481112481112> | Fetched (CSV) |
| S10 | Dry-van truckload rates | Contract $3.24/mile incl. fuel (anchor for truck bids); spot $3.01/mile; fuel surcharge $0.84/mile; diesel $6.291/gal (Sept-2026) | DAT iQ monthly release, Oct 13 2026, via Finviz: <https://finviz.com/news/401824/dat-truckload-rates-rise-in-september-as-diesel-tops-6-a-gallon> | Fetched |

## Context (shown or cited, not a model input)

| ID | What it says | Source |
|---|---|---|
| S11 | The broad semiconductor-device PPI is **down** 2.2% YoY (Sep-2026). Because the PPI is quality-adjusted, it doesn't track memory spot prices, which is why the model takes DRAM prices from TrendForce rather than this index. | FRED PCU334413334413: <https://fred.stlouisfed.org/series/PCU334413334413> |
| S12 | Air freight carries high-value goods such as electronics. Trucks move most high-value, time-sensitive U.S. freight. Context for the truck/air mode split. | BTS, *Freight Shipments by Mode*: <https://www.bts.gov/topics/freight-transportation/freight-shipments-mode>; BTS Freight Analysis Framework: <https://www.bts.gov/faf> |
| S13 | AI data centers could absorb ~70% of high-end DRAM in 2026; HBM is crowding out conventional DRAM. | Avnet, *Riding the AI Supercycle*: <https://www.avnet.com/integrated/resources/article/2026-memory-shortage-ai-supercycle/> (secondary summary) |
| S14 | SK hynix: 2026 HBM, DRAM and NAND capacity "essentially sold out". | Luminovo, *Memory Chip Shortage 2026*: <https://luminovo.com/resources/blog/memory-chip-shortage> (secondary) |
| S15 | Samsung describes its demand-fulfilment rate as at a record low. | PC Gamer: <https://pcgamer.com/hardware/memory/our-demand-fulfillment-rate-is-now-at-a-record-low-says-samsung-as-it-makes-its-dram-90-percent-more-expensive-than-the-previous-quarter> (secondary) |
| S16 | Other PMIC lead-time estimates: 30–50 weeks (Utmel); PMIC lead times easing to 16–24 weeks (Supplyics). Sources disagree. The model uses S5's 16–40 week range. | Utmel: <https://www.utmel.com/blog/categories/pcb/smd-components-outlook-2026-supply-lead-times-and-sourcing-options>; Supplyics: <https://supplyics-web.pages.dev/insights/market-intelligence/q2-2026-semiconductor-lead-time-pricing-outlook/> |
| S17 | DDR4 16Gb spot history: about $91.78 average on Aug 31 2026, up from about $3.20 in early 2025. | cnyes DRAM quotes: <https://www.cnyes.com/futures/material5.aspx>; Tom's Hardware: <https://tomshardware.com/tech-industry/ddr4-spot-prices-fall-for-first-time-in-nearly-a-year-as-chinese-channel-inventory-clears> |

## What is NOT sourced (hypothetical)

Every company-specific number is invented for the fictional **Aster Networks**:
- products, prices, BOMs and demand
- suppliers B and C and their price multipliers
- the LTA premium and take-or-pay terms
- broker capacity and reject rate
- holding-cost rate
- starting inventory and pipeline
- lanes, volumes, carriers, bid multipliers and capacities
- air rates per lb
- penalties

They are tagged `HYP` in `shortage_lab/data.py`, and METHODOLOGY.md lists them.
