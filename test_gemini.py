import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

description = (
    "Vituscare commits to providing a World Class Dialysis Management Program "
    "that focuses on improving the quality of life of individuals and their families. "
    "Our aim is to provide exemplary Kidney Care that is Available, Accessible & "
    "Affordable in India."
)

prompt = (
    "You are a research analyst. Write a 2-sentence brief about this startup "
    "for a busy investor. Be factual and do not invent details.\n\n"
    f"Company description: {description}"
)

r = httpx.post(
    URL,
    headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
    json={"contents": [{"parts": [{"text": prompt}]}]},
    timeout=120,
)

print("Status:", r.status_code)
if r.status_code == 200:
    print(r.json()["candidates"][0]["content"]["parts"][0]["text"])
else:
    print(r.text[:500])