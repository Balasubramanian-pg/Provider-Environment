select npi
from {{ ref('fct_provider_enrollment') }}
where npi is null
   or length(npi) != 10
   or try_cast(npi as bigint) is null
