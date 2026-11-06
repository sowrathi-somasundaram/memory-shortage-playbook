-- Every lane's monthly loads are fully awarded in every scenario.
with awarded as (
    select scenario, lane, sum(loads) as awarded_loads
    from {{ ref('mart_freight_award') }}
    group by scenario, lane
)
select scenarios.scenario, lanes.lane, lanes.loads_per_month, awarded.awarded_loads
from {{ ref('stg_slip_scenarios') }} as scenarios
cross join {{ ref('stg_lanes') }} as lanes
left join awarded
    on awarded.scenario = scenarios.scenario and awarded.lane = lanes.lane
where coalesce(awarded.awarded_loads, 0) <> lanes.loads_per_month
