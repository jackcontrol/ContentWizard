#!/usr/bin/env python3
"""
AI-Visibility Panel v2 (weekly, API spend opted-in)
===================================================
Asks a Groq compound model (with built-in web search) the 24 buyer-intent
questions in site_contract.yaml -> visibility.questions and records, per
category, whether Enormous Door is mentioned and in what context.

Outputs:
  state/visibility.csv        — one row per question per run (trendline)
  state/visibility_gaps.json  — questions where the brand was NOT
                                mentioned; consumed by content_engine.py
  reports/visibility.md       — latest panel with category scoreboard
                                and run-over-run deltas
  visibility_alert.md         — written ONLY when share of voice drops
                                by >= visibility.share_drop_alert vs the
                                previous run (workflow opens an issue)

Requires GROQ_API_KEY (repo secret, free at https://console.groq.com).
Exits 0 quietly without it.
Model default groq/compound-mini — Groq's compound systems run web search
server-side, which this probe needs to reflect real web-grounded answers.
Plain llama models on Groq have NO web search; keep VISIBILITY_MODEL set
to a compound model. Docs: https://console.groq.com/docs/compound
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("VISIBILITY_MODEL", "groq/compound-mini")


def ask(question: str, api_key: str) -> str:
    body = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": (
                f"{question}\n\nAnswer the way you would for a real person, "
                "naming the specific services/engineers you would actually recommend."
            ),
        }],
    }
    for attempt in range(3):
        try:
            r = requests.post(API_URL, json=body, timeout=180, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
            if r.status_code == 429:           # rate limited — back off
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"] or ""
        except (requests.RequestException, KeyError, IndexError) as exc:
            if attempt == 2:
                return f"[probe error: {exc}]"
            time.sleep(10)
    return "[probe error: retries exhausted]"


def previous_mentions(csv_path: Path) -> int | None:
    """Total mentions in the most recent prior run (by date), or None."""
    if not csv_path.exists():
        return None
    by_date = defaultdict(int)
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            by_date[row["date"]] += (row["mentioned"] == "True")
    if not by_date:
        return None
    return by_date[max(by_date)]


def main() -> int:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("visibility: GROQ_API_KEY not set — skipping (optional module).")
        return 0

    contract = yaml.safe_load(Path("site_contract.yaml").read_text())
    vis = contract.get("visibility") or {}
    raw_questions = vis.get("questions") or []
    brand_terms = [t.lower() for t in (vis.get("brand_terms") or [])]
    drop_alert = int(vis.get("share_drop_alert", 0) or 0)

    # Accept both plain strings and {category, q} entries.
    panel = []
    for entry in raw_questions:
        if isinstance(entry, str):
            panel.append(("general", entry))
        else:
            panel.append((entry.get("category", "general"), entry.get("q", "")))
    panel = [(c, q) for c, q in panel if q]
    if not panel:
        print("visibility: no questions configured — skipping.")
        return 0

    Path("state").mkdir(exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    csv_path = Path("state/visibility.csv")
    prev = previous_mentions(csv_path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows, gaps = [], []
    cat_hits, cat_totals = defaultdict(int), defaultdict(int)
    sections = defaultdict(list)

    for category, q in panel:
        answer = ask(q, api_key)
        low = answer.lower()
        mentioned = any(t in low for t in brand_terms)
        cat_totals[category] += 1
        cat_hits[category] += bool(mentioned)
        snippet = ""
        if mentioned:
            for t in brand_terms:
                idx = low.find(t)
                if idx >= 0:
                    snippet = answer[max(0, idx - 120): idx + 220].replace("\n", " ")
                    break
        else:
            gaps.append({"category": category, "question": q,
                         "competitor_answer_excerpt": answer[:600]})
        rows.append({"date": now, "category": category, "question": q,
                     "mentioned": mentioned, "snippet": snippet[:400]})
        sections[category].append(
            f"- {'✅' if mentioned else '❌'} {q}"
            + (f"\n  - …{snippet}…" if snippet else ""))

    total = len(panel)
    hits = sum(cat_hits.values())

    # ---- CSV trendline ----
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "category", "question", "mentioned", "snippet"])
        if new_file:
            w.writeheader()
        w.writerows(rows)

    # ---- gaps feed for the content engine ----
    Path("state/visibility_gaps.json").write_text(json.dumps(
        {"date": now, "gaps": gaps}, indent=2))

    # ---- report ----
    delta = "" if prev is None else f" (previous run: {prev} — {'▲' if hits > prev else '▼' if hits < prev else '='}{abs(hits - prev)})"
    rep = [f"# AI Visibility Panel — {now}",
           f"\n**Share of voice: {hits}/{total}{delta}**\n",
           "| Category | Mentioned |", "|---|---|"]
    for c in sorted(cat_totals):
        rep.append(f"| {c} | {cat_hits[c]}/{cat_totals[c]} |")
    rep.append("")
    for c in sorted(sections):
        rep.append(f"## {c}\n" + "\n".join(sections[c]) + "\n")
    if gaps:
        rep.append(f"\n*{len(gaps)} gap question(s) exported to the content "
                   "engine — next weekly draft targets the top gap.*")
    Path("reports/visibility.md").write_text("\n".join(rep))

    # ---- share-drop alert ----
    alert_path = Path("visibility_alert.md")
    if prev is not None and drop_alert and (prev - hits) >= drop_alert:
        alert_path.write_text(
            f"## 📉 AI share of voice dropped: {prev} → {hits} "
            f"(threshold {drop_alert})\n\nDate: {now}\n\n"
            "See `reports/visibility.md` for which questions were lost. "
            "Common causes: a competitor published targeted content, the "
            "site lost crawler access (check the sentinel report), or an "
            "answer-engine index refresh.\n")
    elif alert_path.exists():
        alert_path.unlink()

    print(f"visibility: {hits}/{total} mentions{delta} — {len(gaps)} gaps exported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
