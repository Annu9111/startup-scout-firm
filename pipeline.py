import os
import json
import time
import datetime
import httpx
from dotenv import load_dotenv

load_dotenv()

CRUSTDATA_KEY = os.getenv("CRUSTDATA_API_KEY")
OLOSTEP_KEY = os.getenv("OLOSTEP_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# ---------- Stage 1: find startups (Crustdata) ----------
def find_startups(limit=5, rounds=None, since="2026-09-01"):
    r = httpx.post(
        "https://api.crustdata.com/company/search",
        headers={
            "authorization": f"Bearer {CRUSTDATA_KEY}",
            "content-type": "application/json",
            "x-api-version": "2025-11-01",
        },
        json={
            "filters": {
                "op": "and",
                "conditions": [
                    {"field": "funding.last_round_type", "type": "in",
                    "value": rounds or ["seed", "series_a", "series_b"]},
                    {"field": "funding.last_fundraise_date", "type": "=>",
                     "value": since},
                ],
            },
            "sorts": [{"field": "funding.last_fundraise_date", "order": "desc"}],
            "limit": limit,
            "fields": [
                "basic_info.name",
                "basic_info.primary_domain",
                "basic_info.description",
                "funding.last_round_type",
                "funding.last_fundraise_date",
                "funding.last_round_amount_usd",
                "headcount.total",
            ],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("companies", [])


# ---------- Stage 2: validate (our own code) ----------
def check_company(company):
    domain = (company.get("basic_info") or {}).get("primary_domain")
    if not domain:
        return False, "no website"
    date_str = (company.get("funding") or {}).get("last_fundraise_date")
    if date_str and date_str > datetime.date.today().isoformat():
        return False, f"funding date is in the future ({date_str})"
    return True, "ok"


# ---------- Stage 3: read the website (Olostep) ----------
def scrape_site(domain):
    try:
        r = httpx.post(
            "https://api.olostep.com/v1/scrapes",
            headers={
                "Authorization": f"Bearer {OLOSTEP_KEY}",
                "Content-Type": "application/json",
            },
            json={"url_to_scrape": f"https://{domain}", "formats": ["markdown"]},
            timeout=90,
        )
        r.raise_for_status()
        text = (r.json().get("result") or {}).get("markdown_content") or ""
        return text[:4000]
    except Exception as e:
        print("   scrape failed:", e)
        return ""


# ---------- Stage 4: write the brief (Gemini) ----------
def write_brief(company, website_text):
    info = company.get("basic_info") or {}
    funding = company.get("funding") or {}
    facts = (
        f"Name: {info.get('name')}\n"
        f"Website: {info.get('primary_domain')}\n"
        f"Description: {info.get('description')}\n"
        f"Team size: {(company.get('headcount') or {}).get('total')}\n"
        f"Last round: {funding.get('last_round_type')}, "
        f"${funding.get('last_round_amount_usd')}, on {funding.get('last_fundraise_date')}\n"
    )
    prompt = (
        "You are a research analyst at an AI research firm. Write a short brief "
        "(max 4 sentences) about this startup for a busy investor: what it does, "
        "its stage, and one notable detail. Use ONLY the facts and website text "
        "below. If something is unknown, say so. Do not invent details.\n\n"
        f"FACTS:\n{facts}\nWEBSITE TEXT:\n{website_text or '(not available)'}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    for attempt in range(3):
        try:
            r = httpx.post(
                url,
                headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=120,
            )
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"   gemini status {r.status_code}, retrying...")
        except httpx.TimeoutException:
            print("   gemini timed out, retrying...")
        time.sleep(5)
    return "Brief could not be generated."


# ---------- Run the whole job ----------
def run_job():
    started = time.time()
    results, skipped = [], []

    print("Finding startups...")
    companies = find_startups(limit=5)
    print(f"Found {len(companies)} companies\n")

    for c in companies:
        name = (c.get("basic_info") or {}).get("name")
        ok, reason = check_company(c)
        if not ok:
            print(f"SKIP {name}: {reason}")
            skipped.append({"name": name, "reason": reason})
            continue

        print(f"WORK {name}")
        domain = c["basic_info"]["primary_domain"]
        site_text = scrape_site(domain)
        brief = write_brief(c, site_text)
        results.append({
            "name": name,
            "website": domain,
            "funding": c.get("funding"),
            "headcount": (c.get("headcount") or {}).get("total"),
            "brief": brief,
            "status": "needs_human_review",
        })
        time.sleep(2)  # be gentle with the free Gemini tier

    report = {
        "seconds_taken": round(time.time() - started, 1),
        "briefs": results,
        "skipped": skipped,
    }
    with open("output.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n===== REPORT =====")
    for item in results:
        print(f"\n{item['name']} ({item['website']})\n{item['brief']}")
    print(f"\nDone in {report['seconds_taken']}s. Saved to output.json")


if __name__ == "__main__":
    run_job()