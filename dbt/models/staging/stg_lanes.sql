select
    cast(lane as varchar)              as lane,
    cast(miles as integer)             as miles,
    cast(loads_per_month as integer)   as loads_per_month,
    cast(buffer_days as integer)       as buffer_days,
    cast(slip_exposed as integer) = 1  as slip_exposed,
    cast(truck_days as integer)        as truck_days,
    cast(air_days as integer)          as air_days
from {{ source('raw', 'raw_lanes') }}
