"""Append ingest/build results to the GitHub Actions job summary."""
import json
import os
from pathlib import Path

lines = [f"## CI mode: `{os.environ.get('CI_MODE', 'unknown')}`"]

registry = Path("ingest/registry.json")
if os.environ.get("SUMMARY_INGEST") == "true" and registry.exists():
    entries = json.loads(registry.read_text())
    total = sum(e.get("row_count", 0) for e in entries)
    lines.append(f"**Ingest:** {len(entries)} datasets · {total:,} rows")

rr = Path("target/run_results.json")
if rr.exists():
    results = json.loads(rr.read_text())["results"]
    counts, problems = {}, []
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] in ("error", "fail"):
            problems.append(f"{r['unique_id']} ({r['status']})")
    lines += ["", "| Status | Count |", "|---|---:|"]
    lines += [f"| {s} | {n} |" for s, n in sorted(counts.items())]
    if problems:
        lines += ["", "**Failures**", ""] + [f"- `{p}`" for p in problems[:25]]
else:
    lines.append("_No run_results.json — build did not reach execution._")

summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a") as f:
        f.write("\n".join(lines) + "\n")
else:
    print("\n".join(lines))
