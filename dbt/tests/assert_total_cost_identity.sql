-- total = landed + holding + lost contribution - ending stock (means are linear, so this holds exactly)
select strategy_key from {{ ref('mart_strategy_results') }}
where abs(total_cost - (landed_cost + holding_cost + lost_contribution - ending_inventory_value)) > 1
   or lost_contribution > lost_revenue
   or total_cost_p5 > total_cost or total_cost > total_cost_p95
