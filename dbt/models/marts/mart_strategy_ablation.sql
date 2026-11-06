-- Remove one lever at a time from the combined hedge (f).
with ablation as (
    select * from {{ ref('stg_ablation') }}
),
base as (
    select total_cost as base_total_cost, fill_rate as base_fill_rate
    from ablation
    where variant = 'Combined hedge (f)'
)
select
    ablation.variant,
    case ablation.variant
        when 'f without broker spot buys'        then 'broker spot-buy trigger'
        when 'f without buy-ahead'               then 'one-month buy-ahead'
        when 'f without LTA (plain A contract)'  then 'allocation contract (LTA) with supplier A'
        when 'f without supplier B (LTA 100%)'   then 'second source (supplier B)'
    end                                                   as lever_removed,
    ablation.fill_rate,
    ablation.stockout_prob,
    ablation.p_line_down,
    ablation.landed_cost,
    ablation.holding_cost,
    ablation.lost_revenue,
    ablation.total_cost,
    ablation.total_cost - base.base_total_cost             as total_cost_vs_f,
    ablation.fill_rate - base.base_fill_rate               as fill_rate_vs_f
from ablation
cross join base
