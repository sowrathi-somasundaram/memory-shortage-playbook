select sum(share_of_sets) as total_share, sum(n_sets) as total_sets
from {{ ref('mart_robustness_summary') }}
having abs(sum(share_of_sets) - 1) > 1e-9
    or sum(n_sets) <> (select max(robustness_scenarios) from {{ ref('stg_run_meta') }})
