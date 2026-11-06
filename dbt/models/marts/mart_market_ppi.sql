-- FRED PPIs with year-over-year change and an index rebased to Jan-2020 = 100.
with ppi as (
    select * from {{ ref('stg_fred_ppi') }}
),
base as (
    select series_id, index_value as base_value
    from ppi
    where observation_date = cast('2020-01-01' as date)
)
select
    ppi.series_id,
    ppi.series_label,
    ppi.observation_date,
    ppi.index_value,
    ppi.index_value / base.base_value * 100 as index_jan2020_100,
    ppi.index_value / lag(ppi.index_value, 12) over (
        partition by ppi.series_id order by ppi.observation_date) - 1 as yoy_change
from ppi
inner join base on ppi.series_id = base.series_id
