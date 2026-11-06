-- On-time target per lane, urgent loads flown, truck diversification, and bid capacity.
with lane_service as (
    select scenario, lane, lane_loads_per_month,
           sum(loads * on_time_rate) / sum(loads) as on_time_rate,
           sum(case when mode = 'air' then loads else 0 end) as air_loads
    from {{ ref('mart_freight_award') }}
    group by scenario, lane, lane_loads_per_month
),
meta as (select on_time_target, max_lane_share from {{ ref('stg_run_meta') }})
select lane_service.scenario, lane_service.lane, 'on-time' as failed_check
from lane_service cross join meta
where lane_service.on_time_rate < meta.on_time_target - 1e-9
union all
select lane_service.scenario, lane_service.lane, 'urgent not flown'
from lane_service
inner join {{ ref('mart_freight_lanes') }} as lanes
    on lanes.scenario = lane_service.scenario and lanes.lane = lane_service.lane
where lane_service.air_loads + lanes.unrecoverable_loads < lanes.urgent_loads
union all
select award.scenario, award.lane, 'diversification'
from {{ ref('mart_freight_award') }} as award cross join meta
where award.mode = 'truck' and award.lane_loads_per_month >= 10
  and award.loads > meta.max_lane_share * award.lane_loads_per_month + 1e-9
union all
select award.scenario, award.lane, 'lane capacity'
from {{ ref('mart_freight_award') }} as award
left join {{ ref('stg_carrier_bids') }} as bids
    on bids.carrier = award.carrier and bids.lane = award.lane
where bids.lane_capacity is null or award.loads > bids.lane_capacity
