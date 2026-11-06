select
    cast(scenario as varchar)               as scenario,
    cast(mean_slip_days as double)          as mean_slip_days,
    cast(status as varchar)                 as solver_status,
    cast(urgent_loads as integer)           as urgent_loads,
    cast(air_loads as integer)              as air_loads,
    cast(unrecoverable_loads as integer)    as unrecoverable_loads,
    cast(late_even_by_air as integer)       as late_even_by_air,
    cast(optimized_freight as double)       as optimized_freight,
    cast(incumbent_freight as double)       as incumbent_freight,
    cast(optimized_cost as double)          as optimized_cost,
    cast(incumbent_cost as double)          as incumbent_cost,
    cast(savings as double)                 as savings,
    cast(savings_pct as double)             as savings_pct,
    cast(freight_savings_pct as double)     as freight_savings_pct
from {{ source('raw', 'raw_freight_sweep') }}
