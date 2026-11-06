"""Inputs: public market anchors and the hypothetical company.

Every number is tagged with where it came from:
  * ``source="S#"``  -> a public source listed in SOURCES.md
  * ``source="HYP"`` -> a hypothetical assumption for the fictional company
  * ``source="DER"`` -> derived from sourced numbers (formula given in the note)

The company "Aster Networks" is FICTIONAL. Its products, demand, costs, suppliers
and carriers are invented for illustration and must not be read as real data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COMPANY_NAME = "Aster Networks (hypothetical)"
HYPOTHETICAL_BANNER = (
    "Aster Networks is a FICTIONAL mid-size networking OEM. Its demand, costs, "
    "suppliers and carrier bids are invented. Market anchors (memory prices, lead "
    "times, allocation fill rates, freight rates and price indexes) come from public "
    "sources listed in SOURCES.md."
)

COMPONENTS = ["DRAM", "PMIC"]          # DRAM = DDR4 16Gb package; PMIC = power-management IC
SITES = ["West (Reno WH -> San Jose plant)", "East (Dallas WH -> Austin plant)"]
SITE_SHORT = ["West", "East"]
SUPPLIERS = ["A", "A_LTA", "B", "C"]   # A_LTA = supplier A under an allocation contract


# --------------------------------------------------------------------------------------
# Public market anchors
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Anchor:
    value: float
    unit: str
    source: str
    note: str


MARKET_ANCHORS: dict[str, Anchor] = {
    "ddr4_16gb_spot": Anchor(82.72, "USD per 16Gb package", "S1",
                             "TrendForce/DRAMeXchange DDR4 16Gb (2Gx8) 3200 spot session average, 2026-11-03"),
    "ddr5_16gb_spot": Anchor(61.50, "USD per 16Gb package", "S1",
                             "TrendForce/DRAMeXchange DDR5 16Gb spot session average, 2026-11-03 (context only)"),
    "dram_q4_contract_qoq": Anchor(0.125, "QoQ change", "S2",
                                   "TrendForce Sept-2026 outlook: Q4-2026 conventional DRAM contract +10-15% QoQ (midpoint)"),
    "dram_lead_weeks_tier1": Anchor(52, "weeks", "S3",
                                    "Sourceability Q3-2026: Micron lead times on several technologies reached 52 weeks"),
    "dram_lead_weeks_range_low": Anchor(32, "weeks", "S4",
                                        "VersaLogic 2026 brief: typical memory lead times 32-40+ weeks"),
    "pmic_lead_weeks_low": Anchor(16, "weeks", "S5", "Hubble 2026 guide: PMIC lead times 16-40 weeks"),
    "pmic_lead_weeks_high": Anchor(40, "weeks", "S5", "Hubble 2026 guide: PMIC lead times 16-40 weeks"),
    "fill_rate_hyperscaler": Anchor(0.70, "share of ordered", "S6",
                                    "DigiTimes via Tom's Hardware: hyperscalers receive ~70% of server DRAM ordered"),
    "fill_rate_small_oem": Anchor(0.375, "share of ordered", "S6",
                                  "Same report: channel/smaller OEMs see 35-40% fulfilment (midpoint)"),
    "semi_ppi_yoy": Anchor(0.260, "YoY", "S7",
                           "FRED PCU33443344 (semiconductor & other electronic components PPI), Sep-2026 vs Sep-2025"),
    "semi_ppi_monthly_sd": Anchor(0.0205, "monthly s.d.", "S7",
                                  "Std. dev. of monthly % change of PCU33443344, last 36 months"),
    "truck_ppi_yoy": Anchor(0.179, "YoY", "S8", "FRED PCU484121484121 (long-distance truckload PPI), Sep-2026 YoY"),
    "air_ppi_yoy": Anchor(0.058, "YoY", "S9", "FRED PCU481112481112 (scheduled air freight PPI), Sep-2026 YoY"),
    "dry_van_contract_per_mile": Anchor(3.24, "USD per mile", "S10",
                                        "DAT, Sept-2026 national dry-van contract rate incl. fuel"),
    "dry_van_spot_per_mile": Anchor(3.01, "USD per mile", "S10", "DAT, Sept-2026 national dry-van spot rate"),
}


def load_fred(series_id: str) -> pd.Series:
    """Load a FRED snapshot saved in data/fred (downloaded 2026-11-03)."""
    df = pd.read_csv(DATA_DIR / "fred" / f"{series_id}.csv", parse_dates=["observation_date"])
    return df.set_index("observation_date")[series_id].astype(float)


FRED_SERIES = {
    "PCU33443344": "PPI: Semiconductor & other electronic component mfg",
    "PCU334413334413": "PPI: Semiconductor & related device mfg",
    "PCU484121484121": "PPI: Long-distance truckload trucking",
    "PCU481112481112": "PPI: Scheduled air freight",
}


# --------------------------------------------------------------------------------------
# Hypothetical company: products, BOM, demand
# --------------------------------------------------------------------------------------
PRODUCTS = pd.DataFrame(
    {
        "product": ["SW-48 enterprise switch", "AP-7 Wi-Fi access point", "ER-4 edge router"],
        "price": [4200.0, 650.0, 2100.0],             # HYP, USD per unit
        "other_var_cost": [2300.0, 330.0, 1150.0],    # HYP, variable cost excluding DRAM/PMIC
        "dram_per_unit": [8, 2, 4],                   # HYP, DDR4 16Gb packages per unit
        "pmic_per_unit": [6, 3, 4],                   # HYP
        "demand_west": [700.0, 4000.0, 1000.0],       # HYP, units / month
        "demand_east": [1100.0, 5000.0, 1500.0],      # HYP, units / month
    }
)


def bom() -> np.ndarray:
    """(P, C) units of each component per finished unit."""
    return PRODUCTS[["dram_per_unit", "pmic_per_unit"]].to_numpy(float)


def base_demand() -> np.ndarray:
    """(P, K) baseline monthly demand by product and site."""
    return PRODUCTS[["demand_west", "demand_east"]].to_numpy(float)


def component_demand() -> np.ndarray:
    """(C,) baseline monthly component requirement across both sites."""
    return bom().T @ base_demand().sum(axis=1)


# --------------------------------------------------------------------------------------
# Simulation parameters (one object so robustness checks can perturb any of them)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Params:
    horizon: int = 24                       # months (Nov-2026 .. Oct-2028)
    # --- prices -------------------------------------------------------------------
    # DRAM contract price: spot (S1) x assumed contract/spot ratio (HYP).
    dram_spot0: float = MARKET_ANCHORS["ddr4_16gb_spot"].value
    contract_to_spot: float = 0.75          # HYP: contract trades below spot in a shortage
    pmic_price0: float = 2.40               # HYP
    # DRAM drift: Q4-26 +12.5% QoQ (S2) -> ~4%/mo for 3 months, then decays (HYP extrapolation)
    dram_drift_near: float = (1 + MARKET_ANCHORS["dram_q4_contract_qoq"].value) ** (1 / 3) - 1
    dram_drift_decay: float = 0.85          # HYP: monthly multiplicative decay of the drift after month 3
    dram_price_sd: float = 0.05             # HYP: monthly log-price volatility for DRAM
    # PMIC drift: FRED component PPI YoY (S7) converted to monthly (DER)
    pmic_drift: float = (1 + MARKET_ANCHORS["semi_ppi_yoy"].value) ** (1 / 12) - 1
    pmic_price_sd: float = MARKET_ANCHORS["semi_ppi_monthly_sd"].value
    # Supplier price multipliers vs contract price (HYP)
    price_mult_B: float = 1.10              # second-tier source
    lta_premium: float = 0.15               # allocation-contract premium on supplier A price
    broker_markup: float = 1.10             # broker resells at spot x markup
    # Landed-cost adders as % of purchase value (HYP)
    freight_pct_std: float = 0.02
    freight_pct_air: float = 0.06
    # --- allocation (fraction of a requested order the supplier confirms) ----------
    # Supplier A mean sits between small-OEM (35-40%) and hyperscaler (70%) fill rates (S6).
    fill_mean: dict = field(default_factory=lambda: {
        ("A", "DRAM"): 0.55, ("A", "PMIC"): 0.80,
        ("A_LTA", "DRAM"): 0.92, ("A_LTA", "PMIC"): 0.95,
        ("B", "DRAM"): 0.80, ("B", "PMIC"): 0.88,
        ("C", "DRAM"): 0.85, ("C", "PMIC"): 0.90,
    })
    fill_concentration: float = 25.0        # HYP: Beta(a,b) with a+b = concentration
    order_inflation_cap: float = 1.30       # HYP: supplier won't confirm more than 1.3x the allocation base
    lta_commit: float = 0.90                # HYP: take-or-pay commitment, share of base volume
    broker_cap: float = 0.30                # HYP: broker can source at most 30% of monthly need per month
    broker_reject: float = 0.03             # HYP: share of broker parts failing incoming inspection
    # Allocation shock: AI demand surge cuts fill rates for non-contract supply (HYP)
    shock_prob: float = 0.35
    shock_mult: float = 0.75
    shock_mult_lta: float = 0.95
    # --- lead times in months: {lag: probability} --------------------------------------
    # A DRAM: 8-12 months (~35-52 weeks), spans S3/S4. A PMIC: 4-9 months (16-40 weeks, S5).
    lead: dict = field(default_factory=lambda: {
        ("A", "DRAM"): {8: 0.2, 9: 0.3, 10: 0.25, 11: 0.15, 12: 0.10},
        ("A", "PMIC"): {4: 0.15, 5: 0.25, 6: 0.25, 7: 0.15, 8: 0.1, 9: 0.1},
        ("B", "DRAM"): {5: 0.3, 6: 0.4, 7: 0.3},            # HYP
        ("B", "PMIC"): {3: 0.3, 4: 0.4, 5: 0.3},            # HYP
        ("C", "DRAM"): {1: 0.85, 2: 0.15},                  # HYP broker stock
        ("C", "PMIC"): {1: 0.85, 2: 0.15},
    })
    lead_shift: int = 0                     # robustness: add months to A and B lead times
    # --- demand ---------------------------------------------------------------------
    demand_common_sd: float = 0.08          # HYP: market-wide monthly shock (AR(1))
    demand_common_rho: float = 0.6
    demand_idio_sd: float = 0.12            # HYP: product x site noise
    # --- starting position (same for every strategy) --------------------------------
    init_onhand_months: float = 2.0         # HYP
    init_pipeline_fill: dict = field(default_factory=lambda: {"DRAM": 0.60, "PMIC": 0.85})  # HYP
    # --- economics ------------------------------------------------------------------
    holding_rate_annual: float = 0.25       # HYP: planning rule-of-thumb
    margin_mult: float = 1.0                # robustness: scales lost contribution

    def with_(self, **kw) -> "Params":
        return replace(self, **kw)

    def contract_price0(self) -> np.ndarray:
        return np.array([self.dram_spot0 * self.contract_to_spot, self.pmic_price0])

    def lead_dist(self, supplier: str, comp: str) -> dict[int, float]:
        key = ("A" if supplier == "A_LTA" else supplier, comp)
        dist = self.lead[key]
        shift = self.lead_shift if key[0] in ("A", "B") else 0
        return {max(1, k + shift): v for k, v in dist.items()}

    def mean_lead(self, supplier: str, comp: str) -> float:
        d = self.lead_dist(supplier, comp)
        return float(sum(k * v for k, v in d.items()))

    def max_lead(self) -> int:
        return max(max(self.lead_dist(s, c)) for s in SUPPLIERS for c in COMPONENTS)


# --------------------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    shares: dict               # supplier -> share of the allocation base
    ss_months: float = 1.0     # safety stock in months of mean demand
    buy_ahead_months: float = 0.0
    emergency_spot: bool = False
    description: str = ""


STRATEGIES: list[Strategy] = [
    Strategy("a", "(a) Status quo single-source", {"A": 1.0}, 1.0,
             description="All volume from supplier A at contract price; 1 month safety stock."),
    Strategy("b", "(b) Buy-ahead", {"A": 1.0}, 1.0, buy_ahead_months=3.0,
             description="Status quo plus a one-time broker purchase of 3 months of need at today's spot price."),
    Strategy("c", "(c) Dual-sourcing", {"A": 0.6, "B": 0.4}, 1.0,
             description="60% supplier A, 40% second-tier supplier B (shorter lead, +10% price)."),
    Strategy("d", "(d) Higher safety stock", {"A": 1.0}, 3.0,
             description="Single-source A with a 3-month safety-stock target."),
    Strategy("e", "(e) Allocation contract (LTA)", {"A_LTA": 1.0}, 1.0,
             description="Long-term agreement with A: +15% price, 90% take-or-pay, protected allocation."),
    Strategy("f", "(f) Combined hedge", {"A_LTA": 0.7, "B": 0.3}, 2.0, buy_ahead_months=1.0,
             emergency_spot=True,
             description="LTA on 70% of volume, B on 30%, 1-month buy-ahead, 2-month safety stock, "
                         "and broker spot buys when next month's cover drops below half a month."),
]
STRATEGY_BY_KEY = {s.key: s for s in STRATEGIES}

SERVICE_TARGET = 0.95   # decision rule: cheapest expected total cost with mean fill rate >= 95%


# --------------------------------------------------------------------------------------
# Freight procurement inputs (lanes and carriers are HYPOTHETICAL; truck rates are
# anchored on the DAT Sept-2026 dry-van contract rate, S10)
# --------------------------------------------------------------------------------------
LOAD_LBS = 20_000   # HYP: one shipment = 20,000 lb truckload-equivalent of components/subassemblies

LANES = pd.DataFrame(
    {
        "lane": ["LAX port -> Reno WH", "LAX port -> Dallas WH", "Reno WH -> San Jose plant",
                 "Dallas WH -> Austin plant", "Reno WH -> Austin plant", "Dallas WH -> San Jose plant"],
        "miles": [520, 1435, 255, 195, 1650, 1700],     # approximate road miles
        "loads_per_month": [40, 55, 38, 52, 6, 6],      # HYP
        "buffer_days": [8, 9, 3, 3, 7, 7],              # HYP: days between planned ship and need date
        "slip_exposed": [1, 1, 0, 0, 1, 1],             # local WH->plant lanes are buffered by WH stock
        "truck_days": [2, 3, 1, 1, 4, 4],               # ~500 mi/day team-free transit
        "air_days": [1, 1, 1, 1, 1, 1],                 # next-flight-out incl. pickup/delivery
    }
)

CARRIERS = pd.DataFrame(
    {
        "carrier": ["T1 (incumbent)", "T2", "T3", "T4", "Air X1", "Air X2"],
        "mode": ["truck", "truck", "truck", "truck", "air", "air"],
        "on_time": [0.94, 0.91, 0.87, 0.97, 0.97, 0.95],     # HYP
        "monthly_capacity": [220, 90, 120, 70, 14, 10],      # HYP, loads per month across lanes
    }
)

_TRUCK_MULT = {  # HYP bid as a multiple of the DAT contract rate per mile, by carrier x lane
    "T1 (incumbent)": [1.08, 1.06, 1.10, 1.12, 1.05, 1.05],
    "T2": [0.95, 0.97, 1.00, 0.98, None, 0.99],
    "T3": [0.90, 0.91, 0.93, 0.92, 0.94, None],
    "T4": [1.02, 1.00, None, 1.04, 1.01, 1.02],
}
TRUCK_MIN_CHARGE = 650.0       # HYP minimum per load on short hauls
AIR_RATE_PER_LB = {"Air X1": 0.95, "Air X2": 0.85}   # HYP domestic expedited air, USD/lb
AIR_MIN_MILES = 500            # air carriers only bid lanes of 500+ miles
AIR_SPOT_PREMIUM = 0.30        # HYP: spot air vs contracted air for the incumbent benchmark
MAX_LANE_SHARE = 0.70          # HYP diversification rule for truck carriers on lanes >= 10 loads
ON_TIME_TARGET = 0.93          # HYP minimum volume-weighted on-time rate per lane
LATE_PENALTY = 25_000.0        # HYP cost per load arriving after its need date (line-side disruption)


def carrier_bids() -> pd.DataFrame:
    """Long table of bids: carrier, lane, cost per load, lane capacity."""
    rate = MARKET_ANCHORS["dry_van_contract_per_mile"].value
    rows = []
    for li, lane in LANES.iterrows():
        for _, c in CARRIERS.iterrows():
            if c["mode"] == "truck":
                mult = _TRUCK_MULT[c["carrier"]][li]
                if mult is None:
                    continue
                cost = max(TRUCK_MIN_CHARGE, rate * lane["miles"] * mult)
                cap = int(np.ceil(lane["loads_per_month"] * (0.9 if c["carrier"] != "T1 (incumbent)" else 1.2)))
            else:
                if lane["miles"] < AIR_MIN_MILES:
                    continue
                cost = AIR_RATE_PER_LB[c["carrier"]] * LOAD_LBS * (1 + lane["miles"] / 5000)
                cap = int(c["monthly_capacity"])
            rows.append({"carrier": c["carrier"], "mode": c["mode"], "lane": lane["lane"],
                         "cost_per_load": round(cost, 2), "lane_capacity": cap, "on_time": c["on_time"]})
    return pd.DataFrame(rows)
