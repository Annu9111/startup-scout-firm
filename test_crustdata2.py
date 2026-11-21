import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

r = httpx.post(
    "https://api.crustdata.com/company/search",
    headers={
        "authorization": f"Bearer {os.getenv('CRUSTDATA_API_KEY')}",
        "content-type": "application/json",
        "x-api-version": "2025-11-01",
    },
    json={
        "filters": {
            "op": "and",
            "conditions": [
                {"field": "funding.last_round_type", "type": "in",
                 "value": ["seed", "series_a", "series_b"]},
                {"field": "funding.last_fundraise_date", "type": "=>",
                 "value": "2026-09-01"},
            ],
        },
        "sorts": [{"field": "funding.last_fundraise_date", "order": "desc"}],
        "limit": 3,
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

print("Status:", r.status_code)
print(json.dumps(r.json(), indent=2)[:2500])