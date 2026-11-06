select
    cast(scenario as varchar)              as scenario,
    cast(lane as varchar)                  as lane,
    cast(loads_per_month as integer)       as loads_per_month,
    cast(urgent_share as double)           as urgent_share,
    cast(late_share as double)             as late_share,
    cast(urgent_loads as integer)          as urgent_loads,
    cast(late_loads as integer)            as late_loads,
    cast(unrecoverable_loads as integer)   as unrecoverable_loads,
    cast(air_loads as integer)             as air_loads,
    cast(freight_cost as double)           as freight_cost,
    cast(on_time_rate as double)           as on_time_rate
from {{ source('raw', 'raw_freight_lanes') }}
