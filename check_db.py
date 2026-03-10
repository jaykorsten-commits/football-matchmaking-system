#!/usr/bin/env python
"""One-off script to check what DB URL the app would use."""
import os
from Admin.Database import _get_db_url

u = _get_db_url()
print("URL_has_rds:", "rds." in u)
print("host_local:", "localhost" in u)
