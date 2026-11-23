{% snapshot snp_provider_enrollment %}
{{ config(
    target_schema='snapshots',
    unique_key='enrollment_key',
    strategy='check',
    check_cols=['provider_type_cd', 'provider_type_desc', 'state_cd',
                'first_name', 'mdl_name', 'last_name', 'org_name',
                'multiple_npi_flag', 'pecos_asct_cntl_id'],
    hard_deletes='invalidate'
) }}
select * from {{ ref('fct_provider_enrollment') }}
{% endsnapshot %}
