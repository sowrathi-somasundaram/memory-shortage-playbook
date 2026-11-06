select
    cast(strategy_key as varchar)       as strategy_key,
    cast(strategy_name as varchar)      as strategy_name,
    cast(description as varchar)        as description,
    cast(supplier_shares as varchar)    as supplier_shares,
    cast(ss_months as double)           as ss_months,
    cast(buy_ahead_months as double)    as buy_ahead_months,
    cast(emergency_spot as boolean)     as emergency_spot
from {{ source('raw', 'raw_strategies') }}
