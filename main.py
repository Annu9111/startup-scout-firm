import datetime
import hmac
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pipeline import find_startups, check_company, scrape_site, write_brief, review_brief
from db import save_job, load_job, list_jobs, count_jobs_on
from business import build_report

load_dotenv()

app = FastAPI(title="Startup Scout Firm")

BASE_DIR = Path(__file__).parent
MAX_PARALLEL = 3          # companies researched at the same time
CANDIDATE_FACTOR = 3      # fetch this many times more candidates than requested

# Protection for the public link. Set both in .env locally and in Render's environment.
ACCESS_CODE = os.getenv("ACCESS_CODE", "")                  # empty = open (local development)
DAILY_JOB_LIMIT = int(os.getenv("DAILY_JOB_LIMIT", "20"))   # new jobs allowed per day (UTC)


def require_code(x_access_code: str = Header(default="")):
    if not ACCESS_CODE:
        return
    if not hmac.compare_digest(x_access_code.encode("utf-8"), ACCESS_CODE.encode("utf-8")):
        raise HTTPException(401, "Wrong or missing access code.")


def utc_today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


class JobRequest(BaseModel):
    customer: str = Field(default="demo customer", max_length=80)
    rounds: list[str] = Field(default=["seed", "series_a", "series_b"])
    since: str = "2026-09-01"
    limit: int = Field(default=3, ge=1, le=10)


class Decision(BaseModel):
    action: str  # "approve" or "reject"
    edited_brief: Optional[str] = Field(default=None, max_length=4000)


def process_company(c):
    """Research one company. Runs in a worker thread and never touches the job record."""
    usage = {}
    name = (c.get("basic_info") or {}).get("name")
    try:
        ok, reason = check_company(c)
        if not ok:
            return {"skipped": {"name": name, "reason": reason}, "usage": usage}

        domain = c["basic_info"]["primary_domain"]
        site_text = scrape_site(domain, usage)
        brief = write_brief(c, site_text, usage)
        review = review_brief(c, site_text, brief, usage)
        return {
            "brief": {
                "name": name,
                "website": domain,
                "funding": c.get("funding"),
                "headcount": (c.get("headcount") or {}).get("total"),
                "brief": brief,
                "review": review,
                "site_read": bool(site_text),
                "status": "needs_human_review",
            },
            "usage": usage,
        }
    except Exception as e:
        return {"skipped": {"name": name, "reason": f"processing error ({e})"}, "usage": usage}


def merge_usage(total, part):
    for key, value in part.items():
        total[key] = total.get(key, 0) + value


def run_job(job_id: str, req: JobRequest):
    job = load_job(job_id)
    usage = job.setdefault("usage", {})
    started = time.time()
    try:
        job["status"] = "running"
        job["log"].append("Finding startups")
        save_job(job)

        # Ask for extra candidates, because some records fail the data check.
        fetch = min(req.limit * CANDIDATE_FACTOR, 30)
        candidates = find_startups(fetch, req.rounds, req.since)
        usage["companies_found"] = len(candidates)

        valid = []
        for c in candidates:
            if len(valid) >= req.limit:
                break
            ok, reason = check_company(c)
            if ok:
                valid.append(c)
            else:
                name = (c.get("basic_info") or {}).get("name")
                job["skipped"].append({"name": name, "reason": reason})
                job["log"].append(f"Skipped {name}: {reason}")

        job["log"].append(
            f"Found {len(candidates)} candidates, {len(valid)} passed the data check"
        )
        if valid:
            job["log"].append(f"Researching {len(valid)} startups at the same time")
        save_job(job)

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            futures = [pool.submit(process_company, c) for c in valid]
            for fut in futures:  # collected in the original order
                result = fut.result()
                merge_usage(usage, result["usage"])
                if "skipped" in result:
                    s = result["skipped"]
                    job["skipped"].append(s)
                    job["log"].append(f"Skipped {s['name']}: {s['reason']}")
                else:
                    job["briefs"].append(result["brief"])
                    job["log"].append(f"Finished {result['brief']['name']}")
                save_job(job)

        job["status"] = "awaiting_review" if job["briefs"] else "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job["seconds_taken"] = round(time.time() - started, 1)
        save_job(job)


@app.get("/health")
def health():
    return {
        "service": "Startup Scout Firm",
        "status": "ok",
        "access_code_required": bool(ACCESS_CODE),
    }


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/jobs")
def create_job(req: JobRequest, background: BackgroundTasks, _: None = Depends(require_code)):
    today = utc_today()
    if count_jobs_on(today) >= DAILY_JOB_LIMIT:
        raise HTTPException(429, "The daily job limit has been reached. Please try again tomorrow.")

    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "customer": req.customer,
        "created_date": today,
        "status": "queued",
        "log": [],
        "briefs": [],
        "skipped": [],
        "usage": {},
    }
    save_job(job)
    background.add_task(run_job, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs")
def all_jobs():
    return [
        {
            "id": j["id"],
            "customer": j["customer"],
            "status": j["status"],
            "briefs": len(j["briefs"]),
        }
        for j in list_jobs()
    ]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/jobs/{job_id}/briefs/{index}/decision")
def decide(job_id: str, index: int, decision: Decision, _: None = Depends(require_code)):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "Job is still running. Wait for awaiting_review.")
    if index < 0 or index >= len(job["briefs"]):
        raise HTTPException(404, "Brief not found")
    if decision.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    item = job["briefs"][index]
    if decision.edited_brief:
        item["brief"] = decision.edited_brief
    item["status"] = "approved" if decision.action == "approve" else "rejected"

    if all(b["status"] != "needs_human_review" for b in job["briefs"]):
        job["status"] = "completed"
    save_job(job)
    return item


@app.get("/jobs/{job_id}/report")
def report(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    pending = [b for b in job["briefs"] if b["status"] == "needs_human_review"]
    if pending:
        raise HTTPException(409, f"{len(pending)} brief(s) still need human review")
    return build_report(job)


EXAMPLE_PATH = BASE_DIR / "examples" / "example_report.json"


@app.get("/example")
def example():
    """A saved report from a real job. Public: needs no access code and spends no credits."""
    if not EXAMPLE_PATH.exists():
        raise HTTPException(404, "No example report has been saved yet.")
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))