select
    cast(runs as integer)                            as runs,
    cast(seed as integer)                            as seed,
    cast(recommended as varchar)                     as recommended_by_python,
    cast(target_met as boolean)                      as target_met,
    cast(robustness_scenarios as integer)            as robustness_scenarios,
    cast(robustness_runs_per_scenario as integer)    as robustness_runs_per_scenario,
    cast(params_fingerprint as varchar)              as params_fingerprint,
    cast(generated as varchar)                       as generated_at,
    cast(service_target as double)                   as service_target,
    cast(tie_tolerance as double)                    as tie_tolerance,
    cast(on_time_target as double)                   as on_time_target,
    cast(max_lane_share as double)                   as max_lane_share
from {{ source('raw', 'raw_run_meta') }}
