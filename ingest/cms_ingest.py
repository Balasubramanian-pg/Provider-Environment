"""Discover every Provider Enrollment dataset on data.cms.gov, load into
DuckDB raw schema (all VARCHAR, as published), write ingest/registry.json."""
import argparse, json, re, time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

CATALOG_URL = "https://data.cms.gov/data.json"
THEME = "Provider Enrollment"
API_PAGE_SIZE = 5000          # CMS documented maximum; script auto-detects caps
FLUSH_EVERY = 200_000
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "cms.duckdb"
REGISTRY_PATH = ROOT / "ingest" / "registry.json"
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "cms-provider-enrollment-dbt/1.0"})


def slugify(title: str) -> str:
    s = title.lower().replace("&", " and ")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", s)).strip("_")


def http_json(url, params=None, retries=5):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=180)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def refresh_days(periodicity: str) -> int:
    m = re.search(r"P(\d+(?:\.\d+)?)([DWMY])", periodicity or "")
    if not m:
        return 14
    n, unit = float(m.group(1)), m.group(2)
    return max(1, int(n * {"D": 1, "W": 7, "M": 31, "Y": 366}[unit]))


def latest_csv(distributions):
    candidates = [d for d in distributions
                  if d.get("downloadURL") and
                  (d["downloadURL"].lower().endswith(".csv")
                   or (d.get("format") or "").upper() == "CSV")]
    if not candidates:
        return None
    def stamp(d):
        end = ""
        for t in d.get("temporal") or []:
            end = max(end, t.get("endDate") or "")
        return (d.get("modified") or "", end)
    return max(candidates, key=stamp)["downloadURL"]


def discover():
    catalog = http_json(CATALOG_URL)
    found = []
    for ds in catalog.get("dataset", []):
        if THEME not in (ds.get("theme") or []):
            continue
        dists = ds.get("distribution") or []
        api_url = next((d["accessURL"] for d in dists
                        if (d.get("format") or "").upper() == "API" and d.get("accessURL")), None)
        blob = " ".join(filter(None, [api_url, ds.get("identifier"), ds.get("@id")]))
        m = UUID_RE.search(blob)
        if not m:
            print(f"  skip (no uuid): {ds.get('title')}")
            continue
        found.append({
            "uuid": m.group(1),
            "title": ds["title"],
            "slug": slugify(ds["title"]),
            "api_url": api_url or f"https://data.cms.gov/data-api/v1/dataset/{m.group(1)}/data",
            "csv_url": latest_csv(dists),
            "refresh_days": refresh_days(ds.get("accrualPeriodicity")),
            "landing_page": (ds.get("landingPage") or {}).get("accessURL", ""),
        })
    return sorted(found, key=lambda x: x["slug"])


def fetch_dictionary(uuid):
    try:
        d = http_json(f"https://data.cms.gov/data-api/v1/dataset/{uuid}/dictionary")
        fields = d.get("fields") if isinstance(d, dict) else d
        if isinstance(fields, dict):
            fields = fields.get("fields", [])
        cols = [{"name": f.get("name") or f.get("title"), "type": f.get("type", "string")}
                for f in (fields or []) if isinstance(f, dict) and (f.get("name") or f.get("title"))]
        return cols or None
    except Exception:
        return None


def load_csv(con, slug, url, uuid):
    url_esc = url.replace("'", "''")
    con.execute(f"""
        CREATE OR REPLACE TABLE raw."{slug}" AS
        SELECT *, '{uuid}' AS _dataset_uuid, current_timestamp AS _loaded_at,
               '{url_esc}' AS _source_url
        FROM read_csv('{url_esc}', header = true, all_varchar = true, auto_detect = true)
    """)


def load_api(con, slug, api_url, uuid, loaded_at):
    offset, size, first, created, total, buf = 0, API_PAGE_SIZE, True, False, 0, []
    while True:
        page = http_json(api_url, {"size": size, "offset": offset})
        if first and page:
            size = min(size, len(page))   # server may cap below requested size
            first = False
        buf.extend(page)
        last = len(page) < size or not page
        if buf and (len(buf) >= FLUSH_EVERY or last):
            df = pd.DataFrame(buf).astype(object).where(pd.notnull(pd.DataFrame(buf)), None)
            df["_dataset_uuid"], df["_loaded_at"], df["_source_url"] = uuid, loaded_at, api_url
            con.register("_incoming", df)
            if not created:
                con.execute(f'CREATE OR REPLACE TABLE raw."{slug}" AS SELECT * FROM _incoming')
                created = True
            else:
                con.execute(f'INSERT INTO raw."{slug}" BY NAME SELECT * FROM _incoming')
            con.unregister("_incoming")
            total += len(buf)
            buf = []
        if last:
            break
        offset += size
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="slug or uuid; repeatable")
    ap.add_argument("--mode", choices=["auto", "csv", "api"], default="auto")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("INSTALL httpfs; LOAD httpfs; CREATE SCHEMA IF NOT EXISTS raw;")

    registry = {}
    if REGISTRY_PATH.exists():                      # merge so --only runs keep full registry
        registry = {e["slug"]: e for e in json.loads(REGISTRY_PATH.read_text())}

    datasets = discover()
    print(f"discovered {len(datasets)} Provider Enrollment datasets")
    for ds in datasets:
        if args.only and ds["slug"] not in args.only and ds["uuid"] not in args.only:
            continue
        loaded_at = datetime.now(timezone.utc)
        mode = args.mode
        if mode == "auto":
            mode = "csv" if ds["csv_url"] else "api"
        print(f"[{ds['slug']}] loading via {mode} ...")
        try:
            if mode == "csv":
                load_csv(con, ds["slug"], ds["csv_url"], ds["uuid"])
            else:
                load_api(con, ds["slug"], ds["api_url"], ds["uuid"], loaded_at)
        except Exception as e:
            if mode == "csv":                        # fall back to the API
                print(f"  csv failed ({e}); falling back to api")
                load_api(con, ds["slug"], ds["api_url"], ds["uuid"], loaded_at)
                mode = "api"
            else:
                raise
        n = con.execute(f'SELECT count(*) FROM raw."{ds["slug"]}"').fetchone()[0]
        cols = fetch_dictionary(ds["uuid"])
        if cols is None:
            cols = [{"name": r[0], "type": "string"}
                    for r in con.execute(f'DESCRIBE raw."{ds["slug"]}"').fetchall()
                    if not r[0].startswith("_")]
        registry[ds["slug"]] = {**ds, "source_mode": mode, "row_count": n,
                                "loaded_at": loaded_at.isoformat(), "columns": cols}
        print(f"  {n:,} rows, {len(cols)} columns")

    REGISTRY_PATH.write_text(json.dumps(sorted(registry.values(), key=lambda x: x["slug"]), indent=2))
    print(f"registry written: {REGISTRY_PATH}")


if __name__ == "__main__":
    main()
