{% macro duckdb__drop_relation(relation) %}
  {%- call statement('drop_relation') -%}
      drop table if exists {{ relation }}
  {%- endcall -%}
  {{ return(results) }}
{% endmacro %}
