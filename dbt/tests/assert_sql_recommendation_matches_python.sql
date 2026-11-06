-- The SQL decision rule must pick the same strategy as simulation.recommend() in Python.
select results.strategy_key, meta.recommended_by_python
from {{ ref('mart_strategy_results') }} as results
cross join {{ ref('stg_run_meta') }} as meta
where results.is_recommended and results.strategy_key <> meta.recommended_by_python
