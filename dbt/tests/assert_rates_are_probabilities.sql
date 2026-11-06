select strategy_key from {{ ref('mart_strategy_results') }}
where fill_rate not between 0 and 1
   or stockout_prob not between 0 and 1
   or p_line_down not between 0 and 1
   or fill_rate_p5 > fill_rate
