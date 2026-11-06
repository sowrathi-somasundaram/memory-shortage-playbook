-- Win / tie / lose rates for the recommended strategy, and the average inputs behind each.
with scenarios as (
    select * from {{ ref('mart_robustness_scenarios') }}
),
totals as (
    select count(*) as n_sets from scenarios
)
select
    scenarios.outcome,
    count(*)                                         as n_sets,
    cast(count(*) as double) / max(totals.n_sets)    as share_of_sets,
    cast(sum(case when scenarios.any_meets_target then 1 else 0 end) as integer)
                                                     as n_sets_target_reachable,
    avg(scenarios.fill_a_dram)                       as avg_fill_a_dram,
    avg(scenarios.init_pipeline_fill_dram)           as avg_init_pipeline_fill_dram,
    avg(scenarios.fill_lta_dram)                     as avg_fill_lta_dram,
    avg(scenarios.lta_premium)                       as avg_lta_premium,
    avg(scenarios.dram_qoq)                          as avg_dram_qoq,
    avg(scenarios.broker_markup)                     as avg_broker_markup,
    avg(scenarios.broker_cap)                        as avg_broker_cap,
    avg(scenarios.shock_prob)                        as avg_shock_prob,
    avg(cast(scenarios.lead_shift as double))        as avg_lead_shift,
    avg(scenarios.recommended_total_cost / scenarios.winner_total_cost - 1)
                                                     as avg_cost_gap_to_winner
from scenarios
cross join totals
group by scenarios.outcome
