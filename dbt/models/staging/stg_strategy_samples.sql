select
    cast(strategy_key as varchar)  as strategy_key,
    cast(total_cost as double)     as total_cost,
    cast(fill_rate as double)      as fill_rate
from {{ source('raw', 'raw_strategy_samples') }}
