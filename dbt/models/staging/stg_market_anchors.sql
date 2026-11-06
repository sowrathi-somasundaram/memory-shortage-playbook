select
    cast(anchor_id as varchar)  as anchor_id,
    cast(value as double)       as anchor_value,
    cast(unit as varchar)       as unit,
    cast(source_id as varchar)  as source_id,
    cast(note as varchar)       as note
from {{ source('raw', 'raw_market_anchors') }}
