with enrollments as (
    select * from {{ ref('fct_provider_enrollment') }}
)
select
    npi,
    max(case when is_organization then 1 else 0 end) = 1 as is_organization,
    max(nullif(trim(first_name), '')) as first_name,
    max(nullif(trim(mdl_name), ''))   as mdl_name,
    max(nullif(trim(last_name), ''))  as last_name,
    max(nullif(trim(org_name), ''))   as org_name,
    count(*)                          as enrollment_count,
    count(distinct provider_type_cd)  as provider_type_count,
    string_agg(distinct state_cd, ', ')          as states,
    string_agg(distinct provider_type_cd, ', ')  as provider_type_codes,
    max(_loaded_at) as _loaded_at
from enrollments
group by npi
