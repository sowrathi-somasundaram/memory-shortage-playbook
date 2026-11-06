{% test exactly_one_row(model) %}
    select count(*) as n from {{ model }} having count(*) <> 1
{% endtest %}
