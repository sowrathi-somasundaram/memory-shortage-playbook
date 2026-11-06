select
    freight_lanes.scenario,
    scenarios.mean_slip_days,
    freight_lanes.lane,
    lanes.slip_exposed,
    freight_lanes.loads_per_month,
    freight_lanes.urgent_share,
    freight_lanes.late_share,
    freight_lanes.urgent_loads,
    freight_lanes.air_loads,
    freight_lanes.late_loads,
    freight_lanes.unrecoverable_loads,
    freight_lanes.on_time_rate,
    freight_lanes.freight_cost
from {{ ref('stg_freight_lanes') }} as freight_lanes
inner join {{ ref('stg_slip_scenarios') }} as scenarios
    on freight_lanes.scenario = scenarios.scenario
inner join {{ ref('stg_lanes') }} as lanes
    on freight_lanes.lane = lanes.lane
