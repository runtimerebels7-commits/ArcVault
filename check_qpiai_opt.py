import os
import requests
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv(
    "QPIAI_OPT_BASE_URL",
    "https://opt-server.qpiai.tech/api"
).rstrip("/")

token = os.getenv("QPIAI_OPT_API_KEY", "").strip()

if not token:
    print("Missing QPIAI_OPT_API_KEY in .env")
    raise SystemExit(1)

try:
    response = requests.post(
        f"{base_url}/problems/create",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=20,
    )

    print("HTTP Status:", response.status_code)

    # Do not print request headers or the token.
    # The empty JSON body may produce a validation error.
    print("Response:", response.text[:500])

except requests.RequestException as error:
    print("Connection error:", type(error).__name__)