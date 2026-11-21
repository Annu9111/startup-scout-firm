import os
import httpx
from dotenv import load_dotenv

load_dotenv()

CRUSTDATA_KEY = os.getenv("CRUSTDATA_API_KEY")
OLOSTEP_KEY = os.getenv("OLOSTEP_API_KEY")


def test_crustdata():
    print("\n--- Crustdata: company search ---")
    r = httpx.post(
        "https://api.crustdata.com/company/search",
        headers={
            "authorization": f"Bearer {CRUSTDATA_KEY}",
            "content-type": "application/json",
            "x-api-version": "2025-11-01",
        },
        json={
            "filters": {"field": "basic_info.name", "type": "=", "value": "Crustdata"},
            "limit": 1,
        },
        timeout=30,
    )
    print("Status:", r.status_code)
    print(r.text[:800])


def test_olostep():
    print("\n--- Olostep: scrape a page ---")
    r = httpx.post(
        "https://api.olostep.com/v1/scrapes",
        headers={
            "Authorization": f"Bearer {OLOSTEP_KEY}",
            "Content-Type": "application/json",
        },
        json={"url_to_scrape": "https://example.com", "formats": ["markdown"]},
        timeout=60,
    )
    print("Status:", r.status_code)
    print(r.text[:800])


test_crustdata()
test_olostep()