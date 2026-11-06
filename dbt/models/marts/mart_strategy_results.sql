-- One row per strategy. Applies the pre-registered decision rule in SQL:
-- lowest expected total cost among strategies with mean fill rate >= service target;
-- if none qualifies, lowest total cost overall.
with summary as (
    select * from {{ ref('stg_strategy_summary') }}
),
strategies as (
    select * from {{ ref('stg_strategies') }}
),
meta as (
    select service_target, runs, seed from {{ ref('stg_run_meta') }}
),
status_quo as (
    select
        total_cost      as sq_total_cost,
        fill_rate       as sq_fill_rate,
        stockout_prob   as sq_stockout_prob,
        landed_cost     as sq_landed_cost,
        holding_cost    as sq_holding_cost,
        lost_revenue    as sq_lost_revenue
    from summary
    where strategy_key = 'a'
),
ranked as (
    select
        summary.*,
        strategies.strategy_name,
        strategies.description,
        strategies.supplier_shares,
        strategies.ss_months,
        strategies.buy_ahead_months,
        strategies.emergency_spot,
        meta.runs,
        meta.seed,
        meta.service_target,
        summary.fill_rate >= meta.service_target as meets_service_target,
        row_number() over (
            order by case when summary.fill_rate >= meta.service_target then 0 else 1 end,
                     summary.total_cost
        ) as decision_rank
    from summary
    inner join strategies on summary.strategy_key = strategies.strategy_key
    cross join meta
)
select
    ranked.strategy_key,
    ranked.strategy_name,
    ranked.description,
    ranked.supplier_shares,
    ranked.ss_months,
    ranked.buy_ahead_months,
    ranked.emergency_spot,
    ranked.fill_rate,
    ranked.fill_rate_p5,
    ranked.p_fill_ge_target,
    ranked.stockout_prob,
    ranked.p_line_down,
    ranked.landed_cost,
    ranked.holding_cost,
    ranked.lost_revenue,
    ranked.lost_contribution,
    ranked.ending_inventory_value,
    ranked.total_cost,
    ranked.total_cost_p5,
    ranked.total_cost_p95,
    ranked.meets_service_target,
    ranked.decision_rank,
    ranked.decision_rank = 1                                   as is_recommended,
    ranked.total_cost - status_quo.sq_total_cost               as total_cost_vs_status_quo,
    (ranked.total_cost - status_quo.sq_total_cost) / status_quo.sq_total_cost
                                                               as total_cost_pct_vs_status_quo,
    ranked.fill_rate - status_quo.sq_fill_rate                 as fill_rate_vs_status_quo,
    ranked.stockout_prob - status_quo.sq_stockout_prob         as stockout_prob_vs_status_quo,
    ranked.landed_cost - status_quo.sq_landed_cost             as landed_cost_vs_status_quo,
    ranked.holding_cost - status_quo.sq_holding_cost           as holding_cost_vs_status_quo,
    ranked.lost_revenue - status_quo.sq_lost_revenue           as lost_revenue_vs_status_quo,
    ranked.service_target,
    ranked.runs,
    ranked.seed
from ranked
cross join status_quo
