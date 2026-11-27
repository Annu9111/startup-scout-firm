# Business assumptions. Change these numbers any time; the page updates by itself.
# Our-cost rates are ESTIMATES: check them against each provider's current price page.

PRICE_PER_APPROVED_BRIEF = 5.00        # what the customer pays for each approved brief (USD)
ANALYST_MINUTES_PER_COMPANY = 30       # time a human analyst needs for one company
ANALYST_HOURLY_RATE = 20.00            # analyst cost per hour (USD)

CRUSTDATA_COST_PER_COMPANY = 0.08      # estimate in USD per company record
OLOSTEP_COST_PER_SCRAPE = 0.002        # estimate in USD per page read
GEMINI_INPUT_PER_MILLION = 0.30        # estimate in USD per 1M input tokens
GEMINI_OUTPUT_PER_MILLION = 2.50       # estimate in USD per 1M output tokens


def job_economics(job):
    usage = job.get("usage") or {}
    briefs = job.get("briefs") or []
    skipped = job.get("skipped") or []

    approved = sum(1 for b in briefs if b.get("status") == "approved")
    researched = len(briefs)
    found = usage.get("companies_found", researched + len(skipped))

    crustdata = found * CRUSTDATA_COST_PER_COMPANY
    olostep = usage.get("scrapes", 0) * OLOSTEP_COST_PER_SCRAPE
    gemini = (
        usage.get("gemini_in", 0) / 1_000_000 * GEMINI_INPUT_PER_MILLION
        + usage.get("gemini_out", 0) / 1_000_000 * GEMINI_OUTPUT_PER_MILLION
    )
    our_cost = crustdata + olostep + gemini

    revenue = approved * PRICE_PER_APPROVED_BRIEF
    margin = revenue - our_cost
    human_minutes = researched * ANALYST_MINUTES_PER_COMPANY
    human_cost = human_minutes / 60 * ANALYST_HOURLY_RATE

    return {
        "approved": approved,
        "researched": researched,
        "revenue": round(revenue, 2),
        "our_cost": round(our_cost, 3),
        "cost_breakdown": {
            "crustdata": round(crustdata, 3),
            "olostep": round(olostep, 3),
            "gemini": round(gemini, 3),
        },
        "margin": round(margin, 2),
        "margin_pct": round(margin / revenue * 100) if revenue else None,
        "human_minutes": human_minutes,
        "human_cost": round(human_cost, 2),
        "agent_seconds": job.get("seconds_taken") or 0,
        "assumptions": {
            "price_per_brief": PRICE_PER_APPROVED_BRIEF,
            "analyst_minutes": ANALYST_MINUTES_PER_COMPANY,
            "analyst_rate": ANALYST_HOURLY_RATE,
        },
    }


def build_report(job):
    """The customer-facing report for a finished job (no usage or internal data)."""
    briefs = job.get("briefs") or []
    return {
        "customer": job["customer"],
        "approved": [b for b in briefs if b.get("status") == "approved"],
        "rejected_count": sum(1 for b in briefs if b.get("status") == "rejected"),
        "skipped": job.get("skipped") or [],
        "seconds_taken": job.get("seconds_taken"),
        "economics": job_economics(job),
    }