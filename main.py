import uuid
import time
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from pipeline import find_startups, check_company, scrape_site, write_brief
from db import save_job, load_job, list_jobs

app = FastAPI(title="Startup Scout Firm")


class JobRequest(BaseModel):
    customer: str = "demo customer"
    rounds: list[str] = Field(default=["seed", "series_a", "series_b"])
    since: str = "2026-09-01"
    limit: int = Field(default=3, ge=1, le=10)


class Decision(BaseModel):
    action: str  # "approve" or "reject"
    edited_brief: Optional[str] = None


def run_job(job_id: str, req: JobRequest):
    job = load_job(job_id)
    started = time.time()
    try:
        job["status"] = "running"
        job["log"].append("Finding startups")
        save_job(job)

        companies = find_startups(req.limit, req.rounds, req.since)
        job["log"].append(f"Found {len(companies)} companies")
        save_job(job)

        for c in companies:
            name = (c.get("basic_info") or {}).get("name")
            ok, reason = check_company(c)
            if not ok:
                job["skipped"].append({"name": name, "reason": reason})
                job["log"].append(f"Skipped {name}: {reason}")
                save_job(job)
                continue

            job["log"].append(f"Researching {name}")
            save_job(job)
            domain = c["basic_info"]["primary_domain"]
            site_text = scrape_site(domain)
            brief = write_brief(c, site_text)
            job["briefs"].append({
                "name": name,
                "website": domain,
                "funding": c.get("funding"),
                "headcount": (c.get("headcount") or {}).get("total"),
                "brief": brief,
                "status": "needs_human_review",
            })
            save_job(job)
            time.sleep(2)

        job["status"] = "awaiting_review"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job["seconds_taken"] = round(time.time() - started, 1)
        save_job(job)


@app.get("/")
def health():
    return {"service": "Startup Scout Firm", "status": "ok"}


@app.post("/jobs")
def create_job(req: JobRequest, background: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "customer": req.customer,
        "status": "queued",
        "log": [],
        "briefs": [],
        "skipped": [],
    }
    save_job(job)
    background.add_task(run_job, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs")
def all_jobs():
    return [
        {"id": j["id"], "customer": j["customer"], "status": j["status"],
         "briefs": len(j["briefs"])}
        for j in list_jobs()
    ]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/jobs/{job_id}/briefs/{index}/decision")
def decide(job_id: str, index: int, decision: Decision):
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
    return {
        "customer": job["customer"],
        "approved": [b for b in job["briefs"] if b["status"] == "approved"],
        "rejected_count": sum(1 for b in job["briefs"] if b["status"] == "rejected"),
        "skipped": job["skipped"],
        "seconds_taken": job.get("seconds_taken"),
    }