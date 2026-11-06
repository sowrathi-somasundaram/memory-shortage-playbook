-- One row per random assumption set, with the recommended strategy's cost gap to the winner.
with robustness as (
    select * from {{ ref('stg_robustness') }}
),
meta as (
    select recommended_by_python as recommended_key from {{ ref('stg_run_meta') }}
)
select
    robustness.*,
    meta.recommended_key,
    case meta.recommended_key
        when 'a' then robustness.total_cost_a when 'b' then robustness.total_cost_b
        when 'c' then robustness.total_cost_c when 'd' then robustness.total_cost_d
        when 'e' then robustness.total_cost_e when 'f' then robustness.total_cost_f
    end                                                       as recommended_total_cost,
    case robustness.winner_key
        when 'a' then robustness.total_cost_a when 'b' then robustness.total_cost_b
        when 'c' then robustness.total_cost_c when 'd' then robustness.total_cost_d
        when 'e' then robustness.total_cost_e when 'f' then robustness.total_cost_f
    end                                                       as winner_total_cost
from robustness
cross join meta
