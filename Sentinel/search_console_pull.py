#!/usr/bin/env python3
"""
search_console_pull.py — OPTIONAL weekly pull of real Google Search
data (queries, clicks, impressions, position) into the repo trendline.
Deterministic; free; the only Google-side setup is a service account.

Setup (one-time, ~15 min):
  1. Google Cloud Console -> create project -> enable "Search Console API".
  2. Create a Service Account -> create a JSON key.
  3. In Search Console -> Settings -> Users -> add the service account's
     email as a user (Full or Restricted).
  4. Repo secrets:  GSC_SERVICE_ACCOUNT_JSON  (paste the whole JSON)
                    GSC_SITE_URL              (e.g. sc-domain:enormousdoor.com
                                               or https://enormousdoor.com/)

Outputs: state/gsc.csv (trend), reports/search_console.md (latest).
Exits 0 quietly if secrets are absent.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    sa_json = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    site = os.environ.get("GSC_SITE_URL", "").strip()
    if not sa_json or not site:
        print("gsc: secrets not configured — skipping (optional module).")
        return 0

    from google.oauth2 import service_account          # lazy import
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    end = date.today() - timedelta(days=2)             # GSC data lags ~2 days
    start = end - timedelta(days=27)
    resp = svc.searchanalytics().query(siteUrl=site, body={
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["query"], "rowLimit": 50,
    }).execute()

    rows = resp.get("rows", [])
    Path("state").mkdir(exist_ok=True)
    csv_path = Path("state/gsc.csv")
    new = not csv_path.exists()
    with open(csv_path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["pulled", "window_end", "query", "clicks", "impressions", "position"])
        for r in rows:
            w.writerow([date.today().isoformat(), end.isoformat(),
                        r["keys"][0], r.get("clicks", 0),
                        r.get("impressions", 0), round(r.get("position", 0), 1)])

    Path("reports").mkdir(exist_ok=True)
    lines = [f"# Search Console — 28 days ending {end}",
             "", "| Query | Clicks | Impr. | Pos. |", "|---|---|---|---|"]
    for r in rows[:25]:
        lines.append(f"| {r['keys'][0]} | {r.get('clicks', 0)} | "
                     f"{r.get('impressions', 0)} | {round(r.get('position', 0), 1)} |")
    Path("reports/search_console.md").write_text("\n".join(lines) + "\n")
    print(f"gsc: {len(rows)} queries pulled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
