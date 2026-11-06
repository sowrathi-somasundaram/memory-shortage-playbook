select
    cast(scenario as varchar)         as scenario,
    cast(mean_slip_days as double)    as mean_slip_days
from {{ source('raw', 'raw_slip_scenarios') }}
