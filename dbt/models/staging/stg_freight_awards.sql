select
    cast(scenario as varchar)        as scenario,
    cast(carrier as varchar)         as carrier,
    cast(lane as varchar)            as lane,
    cast(mode as varchar)            as mode,
    cast(loads as integer)           as loads,
    cast(cost_per_load as double)    as cost_per_load,
    cast(on_time as double)          as on_time_rate,
    cast(cost as double)             as cost
from {{ source('raw', 'raw_freight_awards') }}
