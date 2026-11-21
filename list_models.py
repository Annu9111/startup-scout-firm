import os
import httpx
from dotenv import load_dotenv

load_dotenv()

r = httpx.get(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": os.getenv("GEMINI_API_KEY")},
    timeout=30,
)

print("Status:", r.status_code)
if r.status_code == 200:
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print(m["name"])
else:
    print(r.text[:500])