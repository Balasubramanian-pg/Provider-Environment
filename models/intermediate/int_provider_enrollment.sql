with source as (
    select * from {{ ref('stg_cms__medicare_fee_for_service_public_provider_enrollment') }}
),
ranked as (
    select *,
           row_number() over (partition by npi, enrlmt_id order by _loaded_at desc) as row_rank
    from source
)
select npi, enrlmt_id, pecos_asct_cntl_id, multiple_npi_flag,
       provider_type_cd, provider_type_desc, state_cd,
       first_name, mdl_name, last_name, org_name,
       _dataset_uuid, _loaded_at
from ranked
where row_rank = 1
