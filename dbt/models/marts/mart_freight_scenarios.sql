select
    scenario,
    mean_slip_days,
    solver_status,
    urgent_loads,
    air_loads,
    unrecoverable_loads,
    late_even_by_air,
    optimized_freight,
    incumbent_freight,
    incumbent_freight - optimized_freight      as freight_savings,
    freight_savings_pct,
    optimized_cost,
    incumbent_cost,
    savings                                    as total_savings,
    savings_pct                                as total_savings_pct
from {{ ref('stg_freight_sweep') }}
