DBT = dbt --profiles-dir .

.PHONY: setup ingest generate build refresh docs
setup:
	pip install -r requirements.txt
ingest:
	python ingest/cms_ingest.py
generate:
	python ingest/generate_staging.py
build:
	$(DBT) deps
	$(DBT) build
refresh: ingest generate build
docs:
	$(DBT) docs generate
	$(DBT) docs serve
