with enrolled as (
    select distinct npi from {{ ref('fct_provider_enrollment') }}
    where npi is not null and npi <> ''
),
order_ref as (
    select distinct npi from {{ ref('stg_cms__order_and_referring') }}
    where npi is not null and npi <> ''
),
opt_out as (
    select distinct npi from {{ ref('stg_cms__opt_out_affidavits') }}
    where npi is not null and npi <> ''
),
revoked as (
    select distinct npi from {{ ref('stg_cms__revoked_medicare_providers_and_suppliers') }}
    where npi is not null and npi <> ''
),
otp as (
    select distinct npi from {{ ref('stg_cms__opioid_treatment_program_providers') }}
    where npi is not null and npi <> ''
),
hit as (
    select distinct npi from {{ ref('stg_cms__home_infusion_therapy_providers') }}
    where npi is not null and npi <> ''
),
universe as (
    select npi from enrolled
    union select npi from order_ref
    union select npi from opt_out
    union select npi from revoked
    union select npi from otp
    union select npi from hit
)
select
    u.npi,
    e.npi is not null as is_enrolled_ffs,
    o.npi is not null as can_order_refer,
    oo.npi is not null as has_opt_out_affidavit,
    r.npi is not null as is_revoked,
    t.npi is not null as is_otp_provider,
    h.npi is not null as is_home_infusion_provider
from universe u
left join enrolled  e  on u.npi = e.npi
left join order_ref o  on u.npi = o.npi
left join opt_out   oo on u.npi = oo.npi
left join revoked   r  on u.npi = r.npi
left join otp       t  on u.npi = t.npi
left join hit       h  on u.npi = h.npi
