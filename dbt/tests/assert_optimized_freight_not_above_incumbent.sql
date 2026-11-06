select scenario from {{ ref('mart_freight_scenarios') }}
where optimized_cost > incumbent_cost + 1e-6
