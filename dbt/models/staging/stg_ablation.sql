select
    cast(variant as varchar)          as variant,
    cast(fill_rate as double)         as fill_rate,
    cast(stockout_prob as double)     as stockout_prob,
    cast(line_down as double)         as p_line_down,
    cast(total_cost as double)        as total_cost,
    cast(landed_cost as double)       as landed_cost,
    cast(holding_cost as double)      as holding_cost,
    cast(lost_revenue as double)      as lost_revenue
from {{ source('raw', 'raw_ablation') }}
