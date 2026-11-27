"""Save a finished job as the public example report.

Usage (from the project folder, with the venv active):
    python make_example.py JOB_ID

The job must be fully reviewed (status "completed"). The file is written to
examples/example_report.json, which you commit to GitHub so the live site can show it.
"""
import json
import sys
from pathlib import Path

from business import build_report
from db import load_job

if len(sys.argv) != 2:
    sys.exit("Usage: python make_example.py JOB_ID")

job = load_job(sys.argv[1])
if not job:
    sys.exit(f"No job with id {sys.argv[1]} in jobs.db")
if any(b.get("status") == "needs_human_review" for b in job.get("briefs", [])):
    sys.exit("This job still has briefs waiting for review. Finish reviewing it first.")
if not any(b.get("status") == "approved" for b in job.get("briefs", [])):
    sys.exit("This job has no approved briefs, so it would make an empty example.")

out = Path(__file__).parent / "examples" / "example_report.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(build_report(job), indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Saved {out}")