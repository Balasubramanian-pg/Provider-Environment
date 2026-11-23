"""registry.json -> models/staging/{sources.yml, stg_cms__*.sql, _stg_cms__models.yml}."""
import json, re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "ingest" / "registry.json").read_text())
STAGING = ROOT / "models" / "staging"
STAGING.mkdir(parents=True, exist_ok=True)

# Columns that must stay VARCHAR regardless of dictionary type (identifiers, codes).
ID_LIKE = re.compile(r"(^npi$|_id$|_cd$|_flag$|_zip$|_phone$|_ccn$)")

KNOWN_TESTS = {
    "medicare_fee_for_service_public_provider_enrollment": {
        "not_null": ["npi", "enrlmt_id"], "unique_combo": ["npi", "enrlmt_id"]},
    "order_and_referring": {"not_null": ["npi"], "unique_warn": ["npi"]},
    "opt_out_affidavits": {"not_null": ["npi"]},
    "revoked_medicare_providers_and_suppliers": {"not_null": ["npi"]},
    "opioid_treatment_program_providers": {"not_null": ["npi"]},
    "home_infusion_therapy_providers": {"not_null": ["npi"]},
}


def normalize(name):
    s = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")
    return f"c_{s}" if s[0].isdigit() else s


def sql_type(raw_name, dtype):
    name = raw_name.lower()
    if ID_LIKE.search(name):
        return "varchar"
    t = (dtype or "string").lower()
    if t == "date":
        return "date"
    if t in ("datetime", "timestamp"):
        return "timestamp"
    if t in ("integer", "int", "bigint"):
        return "bigint"
    if t in ("number", "float", "double", "decimal"):
        return "double"
    if t in ("boolean", "bool"):
        return "boolean"
    if "date" in name:
        return "date"
    return "varchar"


sources = {"version": 2, "sources": [{
    "name": "cms_provider_enrollment",
    "database": "cms",            # duckdb file stem; change for your warehouse
    "schema": "raw",
    "loaded_at_field": "_loaded_at",
    "description": "All data.cms.gov datasets tagged Provider Enrollment, loaded by ingest/cms_ingest.py.",
    "tables": [],
}]}
models = {"version": 2, "models": []}

for ds in REGISTRY:
    slug = ds["slug"]
    days = ds.get("refresh_days", 14)
    sources["sources"][0]["tables"].append({
        "name": slug,
        "description": ds["title"],
        "meta": {"uuid": ds["uuid"], "cms_url": ds.get("landing_page", ""),
                 "row_count_at_load": ds.get("row_count")},
        "freshness": {"warn_after": {"count": max(3, int(days * 1.5)), "period": "day"},
                      "error_after": {"count": days * 3, "period": "day"}},
    })

    lines = [f"-- GENERATED from CMS dataset {ds['uuid']} ({ds['title']}).",
             "-- Regenerate with ingest/generate_staging.py; do not hand-edit.",
             "with source as (",
             f"    select * from {{{{ source('cms_provider_enrollment', '{slug}') }}}}",
             "),", "renamed as (", "    select"]
    for col in ds["columns"]:
        alias, t = normalize(col["name"]), sql_type(col["name"], col["type"])
        expr = (f'cast("{col["name"]}" as varchar)' if t == "varchar"
                else f'try_cast("{col["name"]}" as {t})')
        lines.append(f"        {expr} as {alias},")
    lines += ["        _dataset_uuid,", "        _loaded_at,", "        _source_url",
              "    from source", ")", "select * from renamed", ""]
    (STAGING / f"stg_cms__{slug}.sql").write_text("\n".join(lines))

    spec = KNOWN_TESTS.get(slug, {})
    m = {"name": f"stg_cms__{slug}", "description": f"Staged {ds['title']} (typed, renamed).",
         "columns": []}
    for c in spec.get("not_null", []):
        m["columns"].append({"name": c, "data_tests": ["not_null"]})
    for c in spec.get("unique_warn", []):
        m["columns"].append({"name": c, "data_tests": [
            {"unique": {"config": {"severity": "warn"}}}]})
    if spec.get("unique_combo"):
        m["data_tests"] = [{"dbt_utils.unique_combination_of_columns":
                            {"combination_of_columns": spec["unique_combo"]}}]
    models["models"].append(m)

(STAGING / "sources.yml").write_text(yaml.safe_dump(sources, sort_keys=False))
(STAGING / "_stg_cms__models.yml").write_text(yaml.safe_dump(models, sort_keys=False))
print(f"generated staging for {len(REGISTRY)} datasets")
