#!/usr/bin/env python3
"""Debug script: check if DATABASE_URL is in env (for heroku run)."""
import os
print("PORT:", os.environ.get("PORT"))
url = os.environ.get("DATABASE_URL") or ""
print("DATABASE_URL present:", bool(url))
print("Has rds host:", "rds." in url or "amazonaws" in url)
