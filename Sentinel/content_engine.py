#!/usr/bin/env python3
"""
Content Engine (weekly, free-first LLM)
=======================================
Turns AI-visibility gaps into publishing-ready assets.

LLM provider is selected via environment variable LLM_PROVIDER:
  groq      — FREE. Uses Groq API (llama-3.1-8b-instant). Set GROQ_API_KEY.
  ollama    — FREE local. Needs Ollama running on localhost. Set OLLAMA_HOST if not localhost.
  anthropic — Paid. Set ANTHROPIC_API_KEY.

Default: groq (free, works in GitHub Actions, fast).

Outputs:
  content-drafts/YYYY-MM-DD-<slug>.md   — paste-ready page draft
  social-drafts/YYYY-MM-DD.md           — the week's social posts
  state/content_log.json                — topics already produced
  content_alert.md                      — summary for the weekly issue
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

# ── Provider selection ────────────────────────────────────────────────────────

PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

# Groq (free) — https://console.groq.com — get a free key, no card required
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Ollama (free local) — https://ollama.com — runs on your own machine
OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

# Anthropic (paid fallback)
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = os.environ.get("CONTENT_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ── Prompts ───────────────────────────────────────────────────────────────────

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


# ── LLM call router ───────────────────────────────────────────────────────────

def call_llm(prompt: str, max_tokens: int = 2048) -> str:
    """Route to the selected provider. Returns the text response."""
    if PROVIDER == "groq":
        return _call_groq(prompt, max_tokens)
    elif PROVIDER == "ollama":
        return _call_ollama(prompt, max_tokens)
    elif PROVIDER == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {PROVIDER!r}. "
                         f"Choose: groq, ollama, anthropic")


def _call_groq(prompt: str, max_tokens: int) -> str:
    """Groq — free, OpenAI-compatible, uses llama-3.1-8b-instant."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not set. Get a free key at https://console.groq.com "
            "and add it as a GitHub Actions secret named GROQ_API_KEY.")
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    for attempt in range(3):
        try:
            r = requests.post(GROQ_API_URL, json=body, headers=headers, timeout=120)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"Groq rate limit — waiting {wait}s…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as exc:
            if attempt == 2:
                raise RuntimeError(f"Groq API error: {exc}") from exc
            time.sleep(10)
    return ""


def _call_ollama(prompt: str, max_tokens: int) -> str:
    """Ollama — free, local. Requires Ollama running on OLLAMA_HOST."""
    url = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    try:
        r = requests.post(url, json=body, timeout=300)
        r.raise_for_status()
        return r.json().get("response", "")
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Ollama error: {exc}\n"
            f"Is Ollama running at {OLLAMA_HOST}? Run: ollama serve\n"
            f"Is {OLLAMA_MODEL} pulled? Run: ollama pull {OLLAMA_MODEL}") from exc


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    """Anthropic — paid fallback."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(3):
        try:
            r = requests.post(ANTHROPIC_API_URL, json=body,
                              headers=headers, timeout=180)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return "\n".join(b.get("text", "") for b in data.get("content", [])
                             if b.get("type") == "text")
        except requests.RequestException as exc:
            if attempt == 2:
                raise RuntimeError(f"Anthropic API error: {exc}") from exc
            time.sleep(10)
    return ""


# ── Topic selection (unchanged) ───────────────────────────────────────────────

def pick_topic(contract: dict, log: dict) -> tuple[str, str]:
    """Return (topic, source). Gaps first, then backlog; never repeats."""
    done = set(log.get("produced", []))
    gaps_file = Path("state/visibility_gaps.json")
    if gaps_file.exists():
        data = json.loads(gaps_file.read_text())
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    # Check the selected provider has credentials
    if PROVIDER == "groq" and not GROQ_API_KEY:
        print("content engine: GROQ_API_KEY not set.\n"
              "  1. Get a free key at https://console.groq.com\n"
              "  2. Add it as a GitHub Actions secret: GROQ_API_KEY\n"
              "  Skipping this run.")
        return 0
    if PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        print("content engine: ANTHROPIC_API_KEY not set — skipping.")
        return 0
    if PROVIDER == "ollama":
        print(f"content engine: using Ollama at {OLLAMA_HOST} model={OLLAMA_MODEL}")

    contract = yaml.safe_load(Path("site_contract.yaml").read_text())
    voice = (contract.get("content", {}) or {}).get("site_voice", "direct and factual")

    log_path = Path("state/content_log.json")
    log = json.loads(log_path.read_text()) if log_path.exists() else {"produced": []}

    topic, source = pick_topic(contract, log)
    if not topic:
        print("content engine: no unproduced topics remain — add to topics_backlog.")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"content engine [{PROVIDER}]: drafting for topic ({source}): {topic}")

    page   = call_llm(PAGE_PROMPT.format(topic=topic, voice=voice), max_tokens=2048)
    social = call_llm(SOCIAL_PROMPT.format(topic=topic, voice=voice), max_tokens=1024)

    slug_m = re.search(r"URL_SLUG:\s*([a-z0-9-]+)", page)
    slug = (slug_m.group(1) if slug_m
            else re.sub(r"[^a-z0-9]+", "-", topic.lower())[:50].strip("-"))

    Path("content-drafts").mkdir(exist_ok=True)
    Path("social-drafts").mkdir(exist_ok=True)
    draft_path  = Path(f"content-drafts/{now}-{slug}.md")
    social_path = Path(f"social-drafts/{now}.md")

    draft_path.write_text(
        f"<!-- topic: {topic}\n     source: {source}\n"
        f"     provider: {PROVIDER}\n     model: "
        f"{GROQ_MODEL if PROVIDER=='groq' else OLLAMA_MODEL if PROVIDER=='ollama' else ANTHROPIC_MODEL}"
        f"\n     generated: {now} -->\n\n{page}\n")

    social_path.write_text(
        f"# Social drafts — {now}\nTopic: {topic}\nProvider: {PROVIDER}\n\n{social}\n\n"
        "*Schedule via OneUp: in Claude, say \"schedule this week's sentinel "
        "social drafts through OneUp\".*\n")

    log["produced"].append(topic)
    Path("state").mkdir(exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2))

    Path("content_alert.md").write_text(
        f"## 📝 This week's content is drafted — {now}\n\n"
        f"**Topic:** {topic}  \n**Chosen because:** {source}  \n"
        f"**LLM:** {PROVIDER} ({GROQ_MODEL if PROVIDER=='groq' else OLLAMA_MODEL if PROVIDER=='ollama' else ANTHROPIC_MODEL})\n\n"
        f"- Page draft: `{draft_path}`\n"
        f"- Social drafts: `{social_path}`\n\n"
        "**Your 10 minutes:** create the page in Squarespace, paste the body, "
        "set the SEO title/description from the draft header, publish, run a "
        "Search Console live test, request indexing once.\n")

    print(f"content engine: wrote {draft_path} and {social_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
