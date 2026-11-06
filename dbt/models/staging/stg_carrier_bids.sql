select
    cast(carrier as varchar)         as carrier,
    cast(mode as varchar)            as mode,
    cast(lane as varchar)            as lane,
    cast(cost_per_load as double)    as cost_per_load,
    cast(lane_capacity as integer)   as lane_capacity,
    cast(on_time as double)          as on_time_rate
from {{ source('raw', 'raw_carrier_bids') }}
