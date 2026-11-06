select count(*) as n_recommended
from {{ ref('mart_strategy_results') }}
where is_recommended
having count(*) <> 1
