select
    monthly.strategy_key,
    strategies.strategy_name,
    monthly.month_number,
    cast({{ dbt.dateadd('month', 'monthly.month_number - 1', "cast('" ~ var('horizon_start') ~ "' as date)") }} as date)
                                    as month_start_date,
    monthly.fill_mean,
    monthly.fill_p10,
    monthly.fill_p90,
    monthly.dram_cover_months,
    monthly.pmic_cover_months
from {{ ref('stg_strategy_monthly') }} as monthly
inner join {{ ref('stg_strategies') }} as strategies
    on monthly.strategy_key = strategies.strategy_key
