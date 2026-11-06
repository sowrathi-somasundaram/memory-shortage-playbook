select
    cast(strategy_key as varchar)          as strategy_key,
    cast(month as integer)                 as month_number,
    cast(fill_mean as double)              as fill_mean,
    cast(fill_p10 as double)               as fill_p10,
    cast(fill_p90 as double)               as fill_p90,
    cast(dram_cover_months as double)      as dram_cover_months,
    cast(pmic_cover_months as double)      as pmic_cover_months
from {{ source('raw', 'raw_strategy_monthly') }}
