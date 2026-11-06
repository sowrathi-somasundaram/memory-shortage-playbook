select
    cast(strategy_key as varchar)            as strategy_key,
    cast(fill_rate as double)                as fill_rate,
    cast(fill_rate_p5 as double)             as fill_rate_p5,
    cast(p_fill_ge_target as double)         as p_fill_ge_target,
    cast(stockout_prob as double)            as stockout_prob,
    cast(line_down as double)                as p_line_down,
    cast(landed_cost as double)              as landed_cost,
    cast(holding_cost as double)             as holding_cost,
    cast(lost_revenue as double)             as lost_revenue,
    cast(lost_contribution as double)        as lost_contribution,
    cast(ending_inventory_value as double)   as ending_inventory_value,
    cast(total_cost as double)               as total_cost,
    cast(total_cost_p5 as double)            as total_cost_p5,
    cast(total_cost_p95 as double)           as total_cost_p95
from {{ source('raw', 'raw_strategy_summary') }}
