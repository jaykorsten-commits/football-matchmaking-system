#!/usr/bin/env python
"""
Test all Queue API routes. Run from project root with server running:
  uvicorn Admin.main:app --reload
  python scripts/test_routes.py

Set BASE_URL and API_KEY via env or edit below. If API_KEY not set locally, server may not require it.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE_URL = os.environ.get("QUEUE_API_BASE", "https://fastapi-369-dd714db3df0d.herokuapp.com")
API_KEY = os.environ.get("QUEUE_API_KEY", os.environ.get("API_KEY", ""))

headers = {"Content-Type": "application/json"}
if API_KEY:
    headers["X-API-Key"] = API_KEY


def test(name: str, method: str, path: str, json_body=None, expect_ok=True):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = httpx.get(url, headers=headers, timeout=10)
        elif method == "POST":
            r = httpx.post(url, headers=headers, json=json_body or {}, timeout=10)
        else:
            print(f"  SKIP {name} (unknown method)")
            return
        ok = 200 <= r.status_code < 300
        status = "OK" if ok == expect_ok else "FAIL"
        print(f"  {status} {method} {path} -> {r.status_code}")
        if r.status_code >= 400:
            print(f"      {r.text[:200]}")
        return r
    except httpx.ConnectError as e:
        print(f"  FAIL {method} {path} -> Connection error (is server running?)")
        return None
    except Exception as e:
        print(f"  FAIL {method} {path} -> {e}")
        return None


def main():
    print("Testing Queue API at", BASE_URL)
    print("-" * 50)

    # Health
    test("Health", "GET", "/health")

    # Queue routes (some will 422/404 if DB empty or schema mismatch - that's expected)
    test("Join Solo", "POST", "/queue/join/solo", {
        "user_id": 999001,
        "region": "EU",
        "positions": ["CB", "GK"],
        "team_format": "5v5",
        "queue_type": "regular",
    })
    test("Region Status", "POST", "/queue/region/status", {
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
    })
    test("Queue List", "POST", "/queue/list", {
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
        "page": 1,
        "page_size": 10,
    })
    test("Queue Status", "GET", "/queue/status/999001")
    test("Leave Solo", "POST", "/queue/leave/solo", {"user_id": 999001})
    test("Queue Status (after leave)", "GET", "/queue/status/999001")
    test("Cleanup", "POST", "/queue/cleanup/run")

    # Teleport-info and reserve need a valid queue in TELEPORTING - likely 404/400
    test("Teleport Info (expect 404)", "GET", "/queue/eu_99/teleport-info", expect_ok=False)
    test("Reserve (expect 404)", "POST", "/queue/eu_99/reserve", {"job_id": "test-job"}, expect_ok=False)

    # Cleanup: leave queue for any test user that may have joined (idempotent)
    test_user_ids = [999001, 999002, 999003, 999004]
    print("-" * 50)
    print("Cleanup: leaving queue for test users...")
    for uid in test_user_ids:
        try:
            r = httpx.post(f"{BASE_URL}/queue/leave/solo", headers=headers, json={"user_id": uid}, timeout=5)
            if r.status_code in (200, 404):
                print(f"    {uid}: ok")
            else:
                print(f"    {uid}: {r.status_code}")
        except Exception as e:
            print(f"    {uid}: {e}")
    test("Cleanup run", "POST", "/queue/cleanup/run")

    print("-" * 50)
    print("Done. Check output for FAIL (connection/schema/DB issues).")


if __name__ == "__main__":
    main()
