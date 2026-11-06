select
    cast(series_id as varchar)          as series_id,
    cast(series_label as varchar)       as series_label,
    cast(observation_date as date)      as observation_date,
    cast(index_value as double)         as index_value
from {{ source('raw', 'raw_fred_ppi') }}
where index_value is not null
