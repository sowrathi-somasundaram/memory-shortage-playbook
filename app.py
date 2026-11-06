"""Streamlit app: sourcing, stocking and shipping strategy for a (hypothetical) OEM
under AI-driven memory allocation.  Run:  streamlit run app.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shortage_lab import data, simulation, warehouse
from shortage_lab.cache import OUT, params_fingerprint

st.set_page_config(page_title="Memory Shortage Playbook", page_icon="🔌", layout="wide")

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#9a9a94"
OUTCOME_COLOR = {"win": BLUE, "tie": AQUA, "lose": ORANGE}
NAMES = {s.key: s.name for s in data.STRATEGIES}
SHORT = {s.key: s.name.split(") ", 1)[1] for s in data.STRATEGIES}


def money(x: float, digits: int = 1) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x) / 1e6:,.{digits}f}M"


def md(text: str) -> str:
    """Escape dollar signs so Streamlit markdown doesn't render them as LaTeX."""
    return text.replace("$", "\\$")


LEVERS = {  # ablation variant -> plain-English lever it removes
    "f without broker spot buys": "broker spot-buy trigger",
    "f without buy-ahead": "one-month buy-ahead",
    "f without LTA (plain A contract)": "allocation contract (LTA) with supplier A",
    "f without supplier B (LTA 100%)": "second source (supplier B)",
}


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
                      hoverlabel=dict(namelength=-1))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


# --------------------------------------------------------------------------------------
# Data loading. Base-case tables come from the dbt marts: Snowflake when the app has
# Snowflake secrets, otherwise the local mart snapshot in precomputed/marts/ (built by the
# same dbt models on DuckDB). Live what-if runs bypass the marts.
# --------------------------------------------------------------------------------------
def snowflake_secrets() -> dict | None:
    if os.environ.get("MARTS_SOURCE", "").lower() == "local":
        return None
    try:
        return dict(st.secrets["snowflake"]) if "snowflake" in st.secrets else None
    except Exception:  # no secrets file at all
        return None


@st.cache_data(ttl=3600, show_spinner="Reading marts from Snowflake…")
def load_marts(account: str | None):
    """account (None = local only) is the cache key, so changed secrets never reuse stale results."""
    local = warehouse.read_local_marts()
    if account is None:
        return local, "Local mart snapshot (dbt on DuckDB)", None
    try:
        conn = warehouse.connect_snowflake(snowflake_secrets())
        try:
            remote = warehouse.read_snowflake_marts(conn, schema=snowflake_secrets().get("schema", "MARTS"))
        finally:
            conn.close()
        problems = warehouse.check_mart_contract(remote, local)
        if problems:
            return local, "Local mart snapshot (dbt on DuckDB)", "Snowflake marts don't match the app: " + "; ".join(problems)
        return remote, "Snowflake · MEMORY_SHORTAGE.MARTS", None
    except Exception as exc:  # network, auth or timeout: fall back so the app still loads
        return local, "Local mart snapshot (dbt on DuckDB)", f"Snowflake unavailable ({type(exc).__name__}); using local snapshot."


@st.cache_data(show_spinner="Running 10,000-path Monte Carlo…")
def run_live(fill_a: float, lta_premium: float, dram_qoq: float, shock_prob: float, runs: int):
    base = data.Params()
    fill = dict(base.fill_mean)
    fill[("A", "DRAM")] = fill_a
    p = base.with_(fill_mean=fill, lta_premium=lta_premium, shock_prob=shock_prob,
                   dram_drift_near=(1 + dram_qoq) ** (1 / 3) - 1)
    res = simulation.run_all(p, runs=runs, keep_paths=True)
    summary = simulation.summarize(res)
    monthly = pd.DataFrame([{"key": k, "month": t + 1, "fill_mean": r["paths"]["fill"][:, t].mean(),
                             "fill_p10": np.percentile(r["paths"]["fill"][:, t], 10),
                             "dram_cover_months": r["paths"]["cover"][:, t, 0].mean()}
                            for k, r in res.items() for t in range(p.horizon)])
    rng = np.random.default_rng(0)
    idx = rng.choice(runs, size=min(2000, runs), replace=False)
    samples = pd.DataFrame([{"key": k, "total_cost": r["total_cost"][i], "fill_rate": r["fill_rate"][i]}
                            for k, r in res.items() for i in idx])
    return summary, monthly, samples


def tables_from_marts(marts: dict[str, pd.DataFrame]) -> dict:
    """Reshape marts into the frames the page uses."""
    res = marts["mart_strategy_results"].rename(
        columns={"strategy_key": "key", "strategy_name": "strategy", "p_line_down": "line_down"})
    rob = marts["mart_robustness_scenarios"].rename(columns={"winner_key": "winner", "scenario_id": "scenario"})
    return {
        "meta": json.loads((OUT / "meta.json").read_text()),
        "summary": res.set_index("key").sort_index(),
        "monthly": marts["mart_strategy_monthly"].rename(columns={"strategy_key": "key", "month_number": "month"})
                                                 .sort_values(["key", "month"]),
        "samples": pd.read_csv(OUT / "samples.csv"),
        "ablation": marts["mart_strategy_ablation"].sort_values("total_cost_vs_f", key=lambda v: v.abs()),
        "robustness": rob.sort_values("scenario"),
        "robustness_summary": marts["mart_robustness_summary"].set_index("outcome"),
        "freight_sweep": marts["mart_freight_scenarios"].sort_values("mean_slip_days"),
        "freight_award": marts["mart_freight_award"],
        "freight_lanes": marts["mart_freight_lanes"],
        "ppi": marts["mart_market_ppi"],
    }


sf_cfg = snowflake_secrets()
marts, data_source, source_note = load_marts(sf_cfg.get("account") if sf_cfg else None)
pre = tables_from_marts(marts)
base_params = data.Params()
stale = pre["meta"]["params_fingerprint"] != params_fingerprint(base_params)

# --------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Memory Shortage Playbook")
    st.warning(data.HYPOTHETICAL_BANNER, icon="⚠️")
    st.markdown("#### What-if inputs")
    st.caption("Defaults are the base case. Changing any input reruns the Monte Carlo live "
               "(about 2 s per 10,000 paths). The robustness tab always shows the precomputed base case.")
    d_fill = base_params.fill_mean[("A", "DRAM")]
    fill_a = st.slider("Supplier A DRAM allocation fill (mean)", 0.30, 0.90, d_fill, 0.05,
                       help="Published range: 35–40% for smaller OEMs, ~70% for hyperscalers (S6).")
    lta_prem = st.slider("LTA price premium", 0.0, 0.40, base_params.lta_premium, 0.05)
    d_qoq = data.MARKET_ANCHORS["dram_q4_contract_qoq"].value
    dram_qoq = st.slider("Near-term DRAM contract change per quarter", -0.10, 0.30, d_qoq, 0.025,
                         help="TrendForce: Q4-2026 conventional DRAM +10–15% QoQ (S2).")
    shock = st.slider("Probability of a further allocation cut", 0.0, 1.0, base_params.shock_prob, 0.05)
    runs = st.select_slider("Monte Carlo runs", [1000, 2500, 5000, 10000], 10000)
    st.caption(f"Seed fixed at {simulation.DEFAULT_SEED}; every strategy sees the same random paths.")
    st.markdown("#### Data source")
    st.caption(f"Base-case tables: **{data_source}**. What-if runs are computed live.")
    if source_note:
        st.caption(f"⚠️ {source_note}")

is_default = (np.isclose(fill_a, d_fill) and np.isclose(lta_prem, base_params.lta_premium)
              and np.isclose(dram_qoq, d_qoq) and np.isclose(shock, base_params.shock_prob)
              and runs == simulation.DEFAULT_RUNS)
if is_default and not stale:
    summary, monthly, samples = pre["summary"], pre["monthly"], pre["samples"]
else:
    summary, monthly, samples = run_live(fill_a, lta_prem, dram_qoq, shock, runs)

if is_default and not stale:  # decision rule as applied in SQL by mart_strategy_results
    rec = summary.index[summary["is_recommended"].astype(bool)][0]
    rec_ok = bool(summary.loc[rec, "meets_service_target"])
else:
    rec, rec_ok = simulation.recommend(summary)
R = summary.loc[rec]
SQ = summary.loc["a"]
n_runs = runs if not is_default else pre["meta"]["runs"]

st.title("Surviving the AI memory squeeze")
st.caption(f"Sourcing, stocking and freight strategy for **{data.COMPANY_NAME}**, a fictional "
           "mid-size networking OEM. 24-month horizon (Nov-2026 to Oct-2028). Market anchors are "
           "public data; company data is invented.")
if not is_default:
    st.info("Showing a **what-if** run with your sidebar inputs, not the base case.", icon="🔁")
if stale:
    st.error("Precomputed files are out of date with the code's assumptions; showing a live run. "
             "Run `python scripts/precompute.py`.")

tabs = st.tabs(["S&OP summary", "Network & assumptions", "Strategy simulation",
                "Freight procurement", "Robustness", "Market data & sources"])

# --------------------------------------------------------------------------------------
# 1. S&OP summary
# --------------------------------------------------------------------------------------
with tabs[0]:
    st.subheader(f"Recommendation: {NAMES[rec]}")
    if not rec_ok:
        st.error("No strategy reaches the 95% fill-rate target under these inputs; showing the "
                 "lowest expected total cost instead.")
    c = st.columns(5)
    c[0].metric("Fill rate", f"{R.fill_rate:.1%}", f"{(R.fill_rate - SQ.fill_rate) * 100:+.1f} pts vs status quo")
    c[1].metric("Stockout probability (site-month)", f"{R.stockout_prob:.1%}",
                f"{(R.stockout_prob - SQ.stockout_prob) * 100:+.1f} pts", delta_color="inverse")
    c[2].metric("Expected total cost, 24 mo", money(R.total_cost),
                f"{money(R.total_cost - SQ.total_cost)} vs status quo", delta_color="inverse")
    c[3].metric("Landed component cost", money(R.landed_cost),
                f"{money(R.landed_cost - SQ.landed_cost)}", delta_color="inverse")
    c[4].metric("Lost revenue", money(R.lost_revenue), f"{money(R.lost_revenue - SQ.lost_revenue)}",
                delta_color="inverse")
    st.caption("Total cost = landed component cost + holding cost + lost contribution margin − value of "
               "ending stock. Decision rule (fixed in advance): lowest expected total cost among "
               "strategies with mean fill rate ≥ 95%. Means over "
               f"{n_runs:,} simulated paths.")

    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure()
        labels = dict(SHORT)
        pos = {"a": "middle right", "b": "top left", "c": "bottom right", "d": "top center",
               "e": "top right", "f": "middle left"}
        same_ad = (abs(summary.loc["a", "fill_rate"] - summary.loc["d", "fill_rate"]) < 0.002 and
                   abs(summary.loc["a", "total_cost"] / summary.loc["d", "total_cost"] - 1) < 0.002)
        if same_ad:
            labels["a"], labels["d"] = "Status quo ≈ Higher safety stock", ""
        order = [k for k in summary.index if k not in (rec, "a")] + ["a", rec]
        for k in order:
            row = summary.loc[k]
            is_rec, is_sq = k == rec, k == "a"
            fig.add_trace(go.Scatter(x=[row.fill_rate * 100] * 2,
                                     y=[row.total_cost_p5 / 1e6, row.total_cost_p95 / 1e6],
                                     mode="lines", line=dict(color=GRAY, width=2), opacity=0.35,
                                     hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(
                x=[row.fill_rate * 100], y=[row.total_cost / 1e6], mode="markers+text",
                marker=dict(size=14 if is_rec else 11, color=BLUE if is_rec else (ORANGE if is_sq else GRAY),
                            line=dict(width=2, color="white")),
                text=[labels[k]], textposition=pos[k], name=NAMES[k], showlegend=False,
                hovertemplate=f"<b>{NAMES[k]}</b><br>Fill rate %{{x:.1f}}%<br>Total cost $%{{y:.1f}}M"
                              f"<br>P5–P95 cost {money(row.total_cost_p5)}–{money(row.total_cost_p95)}<extra></extra>"))
        fig.add_vline(x=data.SERVICE_TARGET * 100, line_dash="dot", line_color=GRAY,
                      annotation_text="95% service target", annotation_position="bottom right")
        fig.update_layout(title="Cost vs service trade-off (vertical bars: P5–P95 total cost)",
                          xaxis_title="Mean fill rate (%)", yaxis_title="Expected total cost, 24 months ($M)")
        st.plotly_chart(style(fig, 440), width="stretch")
        st.caption("Blue = recommended, orange = status quo, gray = other strategies.")
    with right:
        rob = pre["robustness"]
        counts = rob["outcome"].value_counts()
        n_rob = len(rob)
        loss = rob[rob["outcome"] == "lose"]
        win = rob[rob["outcome"] == "win"]
        abl = pre["ablation"].set_index("variant")
        f_ss1 = abl.loc["f with 1-month safety stock", "total_cost"]
        f_cost = abl.loc["Combined hedge (f)", "total_cost"]
        st.markdown("#### Key risks")
        risks = [
            f"**Near-term gap is unavoidable.** Supplier A's lead time is 8–12 months, so new contracts "
            f"don't land until mid-to-late 2027. Even the recommended plan has a "
            f"{R.line_down:.0%} chance of at least one site-month below 80% of demand.",
            f"**Take-or-pay exposure.** The LTA commits to 90% of base volume. Expected stock left at the "
            f"end is {money(R.ending_inventory_value)} (vs {money(SQ.ending_inventory_value)} today). "
            f"If AI demand cools and prices fall, that stock is worth less.",
            f"**The answer depends on allocation.** In {counts.get('lose', 0)} of {n_rob} alternative "
            f"assumption sets a cheaper plan met the target, typically when A's fill rate averaged "
            f"{loss['fill_a_dram'].mean():.0%} (vs {win['fill_a_dram'].mean():.0%} where (f) won)."
            if len(loss) else "**Allocation could worsen** beyond the tested ranges.",
            f"**Broker parts carry quality risk** (3% assumed incoming-inspection rejects; counterfeit "
            f"exposure is not modelled).",
            f"**Over-buffered.** The 2-month safety stock in (f) does not pay for itself: a 1-month version "
            f"costs {money(f_cost - f_ss1, 2)} less and gives up only {(abl.loc['Combined hedge (f)', 'fill_rate'] - abl.loc['f with 1-month safety stock', 'fill_rate']) * 100:.1f} pts of fill."
            if f_ss1 < f_cost else "",
        ]
        for r_ in risks:
            if r_:
                st.markdown(md(f"- {r_}"))

    st.markdown("#### Recommendation for the supply chain director")
    if rec == "f" and is_default:
        top = (abl["total_cost"] - f_cost).reindex(list(LEVERS)).sort_values(ascending=False)
        lever = LEVERS[top.index[0]]
    st.markdown(md(
        f"Adopt **{NAMES[rec]}** now. Across {n_runs:,} simulated 24-month paths it keeps the "
        f"factories at a {R.fill_rate:.1%} fill rate against {SQ.fill_rate:.1%} under today's single-source "
        f"plan, cutting expected lost revenue from {money(SQ.lost_revenue)} to {money(R.lost_revenue)}. "
        f"It costs {money(R.landed_cost - SQ.landed_cost)} more in landed component spend and "
        f"{money(R.holding_cost - SQ.holding_cost)} more in carrying cost, but expected total cost, "
        f"including lost margin, falls by {money(SQ.total_cost - R.total_cost)} "
        f"({(SQ.total_cost - R.total_cost) / SQ.total_cost:.0%}). "
        + (f"The biggest single lever is the {lever} (removing it adds {money(top.iloc[0])} of expected cost), "
           f"so negotiate that first. " if rec == "f" and is_default else "")
        + "Raising safety stock on its own does nothing while supplier A rations supply, because stock "
        "can't be built from parts that never get confirmed. "
        + (f"The plan won or tied in {(counts.get('win', 0) + counts.get('tie', 0)) / n_rob:.0%} of {n_rob} "
           f"stress-tested assumption sets. Re-check it each quarter against actual allocation confirmations, "
           f"and step back toward a lighter hedge if A starts confirming around {loss['fill_a_dram'].mean():.0%} or more of requests."
           if is_default else "")
    ))
    st.caption("All company figures are hypothetical. The conclusions describe this model's behaviour "
               "under the stated assumptions, not a forecast for any real firm.")

# --------------------------------------------------------------------------------------
# 2. Network & assumptions
# --------------------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Network")
    mu = data.component_demand()
    lab = ["Supplier A (tier-1 memory)", "Supplier B (second-tier)", "Broker C (spot)",
           "LAX port", "Reno WH", "Dallas WH", "San Jose plant", "Austin plant"]
    site_share = (data.bom().T @ data.base_demand())[0] / mu[0]
    fig = go.Figure(go.Sankey(
        node=dict(label=lab, pad=18, thickness=14, color=[BLUE, BLUE, BLUE, GRAY, AQUA, AQUA, ORANGE, ORANGE]),
        link=dict(source=[0, 1, 2, 3, 3, 4, 5], target=[3, 3, 3, 4, 5, 6, 7],
                  value=[0.6, 0.3, 0.1, site_share[0], site_share[1], site_share[0], site_share[1]],
                  color="rgba(128,128,128,0.25)")))
    fig.update_layout(title="Physical flow (link widths illustrative, not a strategy result)")
    st.plotly_chart(style(fig, 320), width="stretch")

    a, b = st.columns(2)
    with a:
        st.markdown("**Products (hypothetical)**")
        st.dataframe(data.PRODUCTS.rename(columns={"other_var_cost": "other variable cost"}),
                     hide_index=True, width="stretch")
        st.caption(f"Monthly component need at baseline: {mu[0]:,.0f} DDR4 16Gb packages and "
                   f"{mu[1]:,.0f} PMICs.")
    with b:
        st.markdown("**Suppliers**")
        p0 = base_params.contract_price0()
        rows = []
        for s, label in [("A", "A: tier-1, allocation-only"), ("A_LTA", "A under LTA"),
                         ("B", "B: second-tier"), ("C", "C: broker / spot")]:
            for ci, comp in enumerate(data.COMPONENTS):
                rows.append({"supplier": label, "part": comp,
                             "price today": round(float(simulation.supplier_price(s, p0[ci], base_params)), 2),
                             "lead (months)": f"{base_params.mean_lead(s, comp):.1f}",
                             "allocation fill (mean)": f"{base_params.fill_mean[(s, comp)]:.0%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.markdown("**Strategies compared**")
    st.dataframe(pd.DataFrame([{"strategy": s.name, "what it does": s.description} for s in data.STRATEGIES]),
                 hide_index=True, width="stretch")
    st.markdown("**Market anchors (public data)**")
    st.dataframe(pd.DataFrame([{"anchor": k, "value": v.value, "unit": v.unit, "source": v.source, "note": v.note}
                               for k, v in data.MARKET_ANCHORS.items()]),
                 hide_index=True, width="stretch")
    st.caption("Source IDs refer to SOURCES.md. Every other input is hypothetical and documented in "
               "METHODOLOGY.md and `shortage_lab/data.py`.")

# --------------------------------------------------------------------------------------
# 3. Strategy simulation
# --------------------------------------------------------------------------------------
with tabs[2]:
    st.subheader(f"Monte Carlo results: {n_runs:,} paths, seed {simulation.DEFAULT_SEED}")
    tbl = summary.assign(strategy=[NAMES[k] for k in summary.index])
    show = pd.DataFrame({
        "Strategy": tbl["strategy"],
        "Fill rate": tbl["fill_rate"].map("{:.1%}".format),
        "Fill rate P5": tbl["fill_rate_p5"].map("{:.1%}".format),
        "Stockout prob. (site-month)": tbl["stockout_prob"].map("{:.1%}".format),
        "P(any line-down month)": tbl["line_down"].map("{:.0%}".format),
        "Landed cost": tbl["landed_cost"].map(money),
        "Holding cost": tbl["holding_cost"].map(money),
        "Lost revenue": tbl["lost_revenue"].map(money),
        "Ending stock value": tbl["ending_inventory_value"].map(money),
        "Total cost (mean)": tbl["total_cost"].map(money),
        "Total cost P5–P95": [f"{money(a_)}–{money(b_)}" for a_, b_ in zip(tbl.total_cost_p5, tbl.total_cost_p95)],
    })
    st.dataframe(show, hide_index=True, width="stretch")
    st.caption("Stockout probability: share of site-months where less than 99.5% of demand could be "
               "built. Line-down month: a site builds under 80% of demand. Unbuilt demand is lost, not backlogged.")

    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        for k in summary.index:
            m = monthly[monthly["key"] == k]
            color = BLUE if k == rec else (ORANGE if k == "a" else GRAY)
            fig.add_trace(go.Scatter(x=m["month"], y=m["fill_mean"] * 100, name=SHORT[k], mode="lines",
                                     line=dict(color=color, width=2.5 if k in (rec, "a") else 1.5),
                                     opacity=1 if k in (rec, "a") else 0.6,
                                     hovertemplate="Month %{x}: %{y:.1f}%"))
        fig.update_layout(title="Mean fill rate by month", xaxis_title="Month (1 = Nov-2026)",
                          yaxis_title="Fill rate (%)", hovermode="x unified")
        st.plotly_chart(style(fig), width="stretch")
    with b:
        comp = summary[["landed_cost", "holding_cost", "lost_contribution"]] / 1e6
        fig = go.Figure()
        for col, name, color in [("landed_cost", "Landed component cost", BLUE),
                                 ("holding_cost", "Holding cost", AQUA),
                                 ("lost_contribution", "Lost contribution margin", ORANGE)]:
            fig.add_trace(go.Bar(y=[SHORT[k] for k in comp.index], x=comp[col], name=name, orientation="h",
                                 marker=dict(color=color, line=dict(width=1, color="white")),
                                 hovertemplate=f"{name}: $%{{x:.1f}}M<extra></extra>"))
        fig.add_trace(go.Scatter(y=[SHORT[k] for k in summary.index], x=summary["total_cost"] / 1e6,
                                 mode="markers", name="Net total (after ending-stock credit)",
                                 marker=dict(symbol="line-ns", size=18, line=dict(width=3, color="#7a7a74")),
                                 hovertemplate="Net total: $%{x:.1f}M<extra></extra>"))
        fig.update_layout(barmode="stack", title="Where the money goes (24-month mean, $M)",
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(fig), width="stretch")

    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        for k in summary.index:
            sm = samples[samples["key"] == k]
            fig.add_trace(go.Box(x=sm["total_cost"] / 1e6, name=SHORT[k], boxpoints=False,
                                 marker_color=BLUE if k == rec else (ORANGE if k == "a" else GRAY)))
        fig.update_layout(title="Distribution of total cost across paths ($M)", showlegend=False,
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(fig, 420), width="stretch")
    with b:
        fig = go.Figure()
        for k in summary.index:
            m = monthly[monthly["key"] == k]
            fig.add_trace(go.Scatter(x=m["month"], y=m["dram_cover_months"], name=SHORT[k], mode="lines",
                                     line=dict(color=BLUE if k == rec else (ORANGE if k == "a" else GRAY),
                                               width=2.5 if k in (rec, "a") else 1.5),
                                     opacity=1 if k in (rec, "a") else 0.6,
                                     hovertemplate="Month %{x}: %{y:.2f} months"))
        fig.update_layout(title="DRAM on hand at month end (months of demand)", xaxis_title="Month",
                          yaxis_title="Months of cover", hovermode="x unified")
        st.plotly_chart(style(fig), width="stretch")

    if is_default:
        st.markdown("#### What drives the combined strategy? (remove one lever at a time)")
        abl = pre["ablation"]
        st.dataframe(pd.DataFrame({
            "Variant": abl["variant"], "Fill rate": abl["fill_rate"].map("{:.1%}".format),
            "Stockout prob.": abl["stockout_prob"].map("{:.1%}".format),
            "Total cost": abl["total_cost"].map(money),
            "Δ vs (f)": abl["total_cost_vs_f"].map(lambda v: f"{v / 1e6:+.2f}M"),
        }), hide_index=True, width="stretch")

# --------------------------------------------------------------------------------------
# 4. Freight procurement
# --------------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Carrier award optimization (integer program, PuLP / CBC)")
    st.caption(md("Lanes, volumes, carriers and bids are hypothetical. Truck bids are multiples (0.90–1.12×) "
               f"of the DAT Sept-2026 dry-van contract rate of ${data.MARKET_ANCHORS['dry_van_contract_per_mile'].value}/mile (S10). "
               "Benchmark = today's routing guide: the incumbent truck carrier on every lane, with urgent loads bought as spot air."))
    sweep = pre["freight_sweep"]
    scen = st.radio("Upstream lead-time slip scenario", list(sweep["scenario"]), horizontal=True)
    sc = sweep.set_index("scenario").loc[scen]
    award = pre["freight_award"][pre["freight_award"]["scenario"] == scen]
    lanes = pre["freight_lanes"][pre["freight_lanes"]["scenario"] == scen]
    freight, inc_freight = sc["optimized_freight"], sc["incumbent_freight"]
    penalty = sc["optimized_cost"] - sc["optimized_freight"]
    c = st.columns(4)
    c[0].metric("Optimized freight / month", money(freight, 3))
    c[1].metric("Incumbent routing guide / month", money(inc_freight, 3))
    c[2].metric("Freight savings", f"{1 - freight / inc_freight:.1%}", money(inc_freight - freight, 3))
    c[3].metric("Air loads (urgent)", f"{int(lanes['air_loads'].sum())}",
                f"{int(lanes['late_loads'].sum())} late even by air", delta_color="off")
    st.caption(md(f"Constraints: every load awarded; lane and carrier capacity; on-time ≥ {data.ON_TIME_TARGET:.0%} "
               f"per lane; no truck carrier above {data.MAX_LANE_SHARE:.0%} of a lane with ≥10 loads; urgent "
               "loads must fly. Loads late even by air carry a "
               f"${data.LATE_PENALTY:,.0f} disruption cost in both plans (${penalty:,.0f} here)."))
    a, b = st.columns([3, 2])
    with a:
        piv = award.pivot_table(index="lane", columns="carrier", values="loads", aggfunc="sum", fill_value=0)
        piv = piv.reindex(data.LANES["lane"]).fillna(0).astype(int)
        st.markdown("**Loads awarded per month**")
        st.dataframe(piv, width="stretch")
        ls = lanes.set_index("lane").reindex(data.LANES["lane"]).reset_index()[["lane", "loads_per_month", "urgent_loads", "air_loads", "late_loads", "on_time_rate", "freight_cost"]]
        st.dataframe(ls.assign(on_time_rate=ls["on_time_rate"].map("{:.1%}".format),
                               freight_cost=ls["freight_cost"].map(lambda v: f"${v:,.0f}")),
                     hide_index=True, width="stretch")
    with b:
        sw = pre["freight_sweep"]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=sw["mean_slip_days"].astype(str) + " d", y=sw["incumbent_freight"] / 1e3,
                             name="Incumbent routing guide", marker_color=GRAY))
        fig.add_trace(go.Bar(x=sw["mean_slip_days"].astype(str) + " d", y=sw["optimized_freight"] / 1e3,
                             name="Optimized award", marker_color=BLUE,
                             customdata=np.c_[sw["air_loads"], sw["freight_savings_pct"] * 100],
                             hovertemplate="$%{y:.0f}k · %{customdata[0]} air loads · saves %{customdata[1]:.1f}%<extra></extra>"))
        fig.update_layout(barmode="group", title="Monthly freight spend as slip grows ($k)",
                          xaxis_title="Mean upstream slip", bargap=0.3)
        st.plotly_chart(style(fig, 360), width="stretch")
        st.caption("As the slip grows, more loads have to fly. Past a point even air arrives late, "
                   "so air volume levels off and the late-load count climbs instead.")

# --------------------------------------------------------------------------------------
# 5. Robustness
# --------------------------------------------------------------------------------------
with tabs[4]:
    rob = pre["robustness"]
    meta = pre["meta"]
    rec0 = meta["recommended"]
    counts = rob["outcome"].value_counts()
    st.subheader(f"How often does {NAMES[rec0]} still win?")
    st.caption(f"{len(rob)} random assumption sets × {meta['robustness_runs_per_scenario']:,} paths each. "
               "Each set redraws 17 inputs (allocation fills, LTA premium, price trend, broker cost and "
               "capacity, lead-time shift, demand volatility, holding rate, shock probability, pipeline, margin) "
               "from the ranges in `shortage_lab/robustness.py`. Same decision rule each time. Tie = within 1% of "
               "the winner's expected cost while meeting the same service test.")
    c = st.columns(4)
    for i, o in enumerate(["win", "tie", "lose"]):
        c[i].metric(o.capitalize(), f"{counts.get(o, 0) / len(rob):.1%}", f"{counts.get(o, 0)} sets", delta_color="off")
    c[3].metric("Sets where any plan hits 95%", f"{rob['any_meets_target'].mean():.0%}")
    a, b = st.columns(2)
    with a:
        w = rob["winner"].value_counts().reindex(list(NAMES), fill_value=0)
        fig = go.Figure(go.Bar(y=[SHORT[k] for k in w.index], x=w.values, orientation="h",
                               marker_color=[BLUE if k == rec0 else GRAY for k in w.index],
                               text=w.values, textposition="outside",
                               hovertemplate="%{y}: %{x} sets<extra></extra>"))
        fig.update_layout(title="Winning strategy by assumption set", yaxis=dict(autorange="reversed"),
                          xaxis=dict(range=[0, w.max() * 1.15]))
        st.plotly_chart(style(fig), width="stretch")
    with b:
        fig = go.Figure()
        for o in ["win", "tie", "lose"]:
            sub = rob[rob["outcome"] == o]
            fig.add_trace(go.Scatter(x=sub["fill_a_dram"] * 100, y=sub["init_pipeline_fill_dram"] * 100,
                                     mode="markers", name=o, marker=dict(color=OUTCOME_COLOR[o], size=8,
                                                                         line=dict(width=1, color="white")),
                                     hovertemplate="A fill %{x:.0f}% · pipeline %{y:.0f}%<extra>" + o + "</extra>"))
        fig.update_layout(title="Outcome vs supplier A allocation and existing pipeline",
                          xaxis_title="Supplier A DRAM fill rate (%)", yaxis_title="Existing DRAM pipeline (% of need)")
        st.plotly_chart(style(fig), width="stretch")
    st.markdown("**Average inputs by outcome**")
    rs = pre["robustness_summary"].reindex(["win", "tie", "lose"])
    st.dataframe(rs[["n_sets", "share_of_sets", "avg_fill_a_dram", "avg_init_pipeline_fill_dram", "avg_fill_lta_dram",
                     "avg_lta_premium", "avg_dram_qoq", "avg_broker_markup", "avg_broker_cap", "avg_shock_prob",
                     "avg_lead_shift", "avg_cost_gap_to_winner"]].round(3), width="stretch")

# --------------------------------------------------------------------------------------
# 6. Market data & sources
# --------------------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Public price indexes (FRED, snapshot 2026-11-03)")
    fig = go.Figure()
    palette = [BLUE, ORANGE, AQUA, "#eda100"]
    ppi = pre["ppi"].sort_values("observation_date")
    for (sid, label), color in zip(data.FRED_SERIES.items(), palette):
        s = ppi[(ppi["series_id"] == sid) & (ppi["observation_date"] >= "2020-01-01")]
        fig.add_trace(go.Scatter(x=s["observation_date"], y=s["index_jan2020_100"], name=f"{label} ({sid})",
                                 line=dict(color=color, width=2),
                                 hovertemplate="%{x|%b %Y}: %{y:.1f}"))
    fig.update_layout(title="Producer price indexes, Jan-2020 = 100", yaxis_title="Index", hovermode="x unified")
    st.plotly_chart(style(fig, 420), width="stretch")
    yoy = ppi.groupby("series_id").last()["yoy_change"]
    st.caption("BLS PPIs are quality-adjusted industry indexes. The broad semiconductor-device PPI "
               f"(PCU334413334413) is {yoy['PCU334413334413']:+.1%} year on year even while DDR4 spot prices "
               "have multiplied, so the model takes DRAM prices from TrendForce rather than the PPI. The components "
               f"PPI (PCU33443344, {yoy['PCU33443344']:+.1%} YoY) drives PMIC price drift. The truckload and air PPIs "
               "give context for freight rates.")
    st.markdown("Full source list with links: **SOURCES.md** in the repository.")
