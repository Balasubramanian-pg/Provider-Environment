select
    state_cd,
    provider_type_cd,
    provider_type_desc,
    count(*) as enrollment_count,
    count(distinct npi) as provider_count,
    sum(case when is_organization then 1 else 0 end) as organization_enrollments
from {{ ref('fct_provider_enrollment') }}
group by state_cd, provider_type_cd, provider_type_desc
