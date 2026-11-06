-- Carrier award lines per slip scenario, with each carrier's share of the lane.
select
    awards.scenario,
    scenarios.mean_slip_days,
    awards.lane,
    lanes.miles,
    lanes.loads_per_month                              as lane_loads_per_month,
    awards.carrier,
    awards.mode,
    awards.carrier = 'T1 (incumbent)'                  as is_incumbent,
    awards.loads,
    cast(awards.loads as double) / lanes.loads_per_month as share_of_lane,
    awards.cost_per_load,
    awards.on_time_rate,
    awards.cost
from {{ ref('stg_freight_awards') }} as awards
inner join {{ ref('stg_slip_scenarios') }} as scenarios
    on awards.scenario = scenarios.scenario
inner join {{ ref('stg_lanes') }} as lanes
    on awards.lane = lanes.lane
