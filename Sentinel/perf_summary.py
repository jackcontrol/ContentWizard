#!/usr/bin/env python3
"""
perf_summary.py — parse Lighthouse JSON outputs, append the trend CSV,
and write perf_alert.md when any category score breaches its threshold.
Deterministic; no API usage. Invoked by the monthly lighthouse workflow.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THRESHOLDS = {"performance": 60, "seo": 90, "accessibility": 80, "best-practices": 80}


def main() -> int:
    reports = sorted(Path("lh-out").glob("*.json"))
    if not reports:
        print("perf: no lighthouse reports found")
        return 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows, breaches = [], []
    for rp in reports:
        data = json.loads(rp.read_text())
        url = data.get("finalDisplayedUrl") or data.get("finalUrl") or rp.stem
        cats = data.get("categories", {})
        scores = {k: round((cats.get(k, {}).get("score") or 0) * 100)
                  for k in THRESHOLDS}
        rows.append((url, scores))
        for cat, score in scores.items():
            if score < THRESHOLDS[cat]:
                breaches.append(f"- **{url}** — {cat}: {score} (threshold {THRESHOLDS[cat]})")

    Path("state").mkdir(exist_ok=True)
    csv_path = Path("state/lighthouse.csv")
    new = not csv_path.exists()
    with open(csv_path, "a") as fh:
        if new:
            fh.write("date,url,performance,seo,accessibility,best_practices\n")
        for url, s in rows:
            fh.write(f"{now},{url},{s['performance']},{s['seo']},"
                     f"{s['accessibility']},{s['best-practices']}\n")

    Path("reports").mkdir(exist_ok=True)
    lines = [f"# Lighthouse — {now}", "", "| Page | Perf | SEO | A11y | Best |", "|---|---|---|---|---|"]
    for url, s in rows:
        lines.append(f"| {url} | {s['performance']} | {s['seo']} | "
                     f"{s['accessibility']} | {s['best-practices']} |")
    Path("reports/lighthouse.md").write_text("\n".join(lines) + "\n")

    alert = Path("perf_alert.md")
    if breaches:
        alert.write_text(f"## 🐢 Lighthouse threshold breach — {now}\n\n"
                         + "\n".join(breaches)
                         + "\n\nSlow/failing pages depress both conversion and "
                           "crawl priority. Trend: `state/lighthouse.csv`.\n")
    elif alert.exists():
        alert.unlink()
    print(f"perf: {len(rows)} pages scored, {len(breaches)} breach(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
