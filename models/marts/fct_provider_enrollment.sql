with enrollment as (
    select * from {{ ref('int_provider_enrollment') }}
)
select
    {{ dbt_utils.generate_surrogate_key(['npi', 'enrlmt_id']) }} as enrollment_key,
    npi,
    enrlmt_id,
    pecos_asct_cntl_id,
    multiple_npi_flag,
    provider_type_cd,
    provider_type_desc,
    split_part(provider_type_desc, ' - ', 1) as provider_category,
    state_cd,
    first_name,
    mdl_name,
    last_name,
    org_name,
    nullif(trim(org_name), '') is not null as is_organization,
    _dataset_uuid,
    _loaded_at
from enrollment
