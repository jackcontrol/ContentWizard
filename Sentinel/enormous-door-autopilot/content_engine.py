#!/usr/bin/env python3
"""
Content Engine (weekly, API spend opted-in)
===========================================
Turns AI-visibility gaps into publishing-ready assets:

  1. ONE page draft per week, targeting the highest-value question
     where the brand was NOT mentioned in the last visibility panel
     (falls back to the contract's topics_backlog). Structured for AI
     retrieval: question-shaped H2s, quotable facts, SEO title/desc,
     internal routing to /launch-contact, /pricing, and
     /technical-faq#mix-prep per the routing guardrails.
  2. FOUR social post drafts tied to the same topic, written for
     scheduling through OneUp.

Outputs:
  content-drafts/YYYY-MM-DD-<slug>.md   — paste-ready page draft
  social-drafts/YYYY-MM-DD.md           — the week's social posts
  state/content_log.json                — topics already produced
  content_alert.md                      — summary for the weekly issue

Honesty note: Squarespace has no page-creation API, so the final
paste-and-publish step is human (~10 minutes/week). Everything up to
that point is automatic.

Requires ANTHROPIC_API_KEY. Exits 0 quietly without it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CONTENT_MODEL", "claude-sonnet-4-6")

PAGE_PROMPT = """You are writing a page for Enormous Door Mastering
(enormousdoor.com) — heavy music mastering by Jack Control (5000+ credits
since 2008), premium "Beyond Heavy" tier with Maor Appelbaum.

VOICE: {voice}

TARGET: this page must become the answer AI search engines and Google cite
for the question: "{topic}"

REQUIREMENTS:
- Question-shaped H2 headings (the exact phrasings people ask).
- Dense, quotable, factual: real numbers, formats, named specs.
- 600-900 words. No fluff, no hype adjectives, no exclamation points.
- Route readers: project inquiries -> /launch-contact; money -> /pricing;
  file-prep detail -> /technical-faq#mix-prep (link, do not duplicate).
- Do NOT contradict live pricing: LP/45min Heavy Mastering is $500
  single-format / $600 full release package; Beyond Heavy LP/45 is $850.
- Output EXACTLY this structure, nothing else:

SEO_TITLE: <max 60 chars>
SEO_DESCRIPTION: <max 158 chars>
URL_SLUG: <lowercase-hyphenated>
H1: <ALL CAPS, distinct from every existing page H1>
---
<page body in markdown, H2s as ##>
"""

SOCIAL_PROMPT = """Write 4 social posts for Enormous Door Mastering promoting
this topic: "{topic}" (new page going live at enormousdoor.com).

VOICE: {voice}

- Post 1: Instagram/Facebook (2-3 sentences + 5 niche hashtags)
- Post 2: X/Threads (under 250 chars, no hashtags)
- Post 3: TikTok caption (1-2 sentences + 4 hashtags)
- Post 4: a question-format post that invites replies from bands

Each ends with a call to action pointing to enormousdoor.com.
Output as a markdown list: "### Post N (platform)" then the text.
"""


def call_claude(prompt: str, api_key: str, max_tokens: int = 2048) -> str:
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(3):
        try:
            r = requests.post(API_URL, json=body, timeout=180, headers={
                "x-api-key": api_key, "anthropic-version": "2023-06-01",
                "content-type": "application/json"})
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return "\n".join(b.get("text", "") for b in data.get("content", [])
                             if b.get("type") == "text")
        except requests.RequestException as exc:
            if attempt == 2:
                raise RuntimeError(f"content engine API error: {exc}") from exc
            time.sleep(10)
    return ""


def pick_topic(contract: dict, log: dict) -> tuple[str, str]:
    """Return (topic, source). Gaps first, then backlog; never repeats."""
    done = set(log.get("produced", []))
    gaps_file = Path("state/visibility_gaps.json")
    if gaps_file.exists():
        data = json.loads(gaps_file.read_text())
        # Prioritize commercially valuable categories first.
        priority = {"pricing": 0, "comparison": 1, "discovery": 2,
                    "process": 3, "brand": 4, "general": 5}
        for gap in sorted(data.get("gaps", []),
                          key=lambda g: priority.get(g.get("category"), 9)):
            q = gap["question"]
            if q not in done:
                return q, f"visibility gap ({gap.get('category')})"
    for topic in (contract.get("content", {}).get("topics_backlog") or []):
        if topic not in done:
            return topic, "backlog"
    return "", ""


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("content engine: ANTHROPIC_API_KEY not set — skipping (optional module).")
        return 0

    contract = yaml.safe_load(Path("site_contract.yaml").read_text())
    voice = (contract.get("content", {}) or {}).get("site_voice", "direct and factual")

    log_path = Path("state/content_log.json")
    log = json.loads(log_path.read_text()) if log_path.exists() else {"produced": []}

    topic, source = pick_topic(contract, log)
    if not topic:
        print("content engine: no unproduced topics remain — add to topics_backlog.")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"content engine: drafting for topic ({source}): {topic}")

    page = call_claude(PAGE_PROMPT.format(topic=topic, voice=voice), api_key)
    social = call_claude(SOCIAL_PROMPT.format(topic=topic, voice=voice),
                         api_key, max_tokens=1024)

    slug_m = re.search(r"URL_SLUG:\s*([a-z0-9-]+)", page)
    slug = slug_m.group(1) if slug_m else re.sub(r"[^a-z0-9]+", "-", topic.lower())[:50].strip("-")

    Path("content-drafts").mkdir(exist_ok=True)
    Path("social-drafts").mkdir(exist_ok=True)
    draft_path = Path(f"content-drafts/{now}-{slug}.md")
    draft_path.write_text(
        f"<!-- topic: {topic}\n     source: {source}\n     generated: {now} -->\n\n{page}\n")
    social_path = Path(f"social-drafts/{now}.md")
    social_path.write_text(
        f"# Social drafts — {now}\nTopic: {topic}\n\n{social}\n\n"
        "*Schedule via OneUp: in Claude, say \"schedule this week's sentinel "
        "social drafts through OneUp\".*\n")

    log["produced"].append(topic)
    Path("state").mkdir(exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2))

    Path("content_alert.md").write_text(
        f"## 📝 This week's content is drafted — {now}\n\n"
        f"**Topic:** {topic}  \n**Chosen because:** {source}\n\n"
        f"- Page draft (paste into a new Squarespace page): `{draft_path}`\n"
        f"- Social drafts (schedule via OneUp): `{social_path}`\n\n"
        "**Your 10 minutes:** create the page in Squarespace, paste the body, "
        "set the SEO title/description from the draft header, publish, run a "
        "Search Console live test, request indexing once. Then tell Claude to "
        "add the new page to `site_contract.yaml` so the sentinel guards it.\n")
    print(f"content engine: wrote {draft_path} and {social_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
