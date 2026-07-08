#!/usr/bin/env python3
"""
Enormous Door Sentinel — MCP Server
===================================
Exposes the sentinel engine to Claude (Desktop / Code / any MCP client)
as on-demand tools. Nothing here is scheduled and nothing calls the
Anthropic API — Claude itself is the intelligence; these tools are its
deterministic hands. Zero background spend.

Setup (Claude Desktop) — add to claude_desktop_config.json:

  {
    "mcpServers": {
      "ed-sentinel": {
        "command": "python",
        "args": ["/ABSOLUTE/PATH/TO/repo/mcp_server.py"],
        "cwd": "/ABSOLUTE/PATH/TO/repo"
      }
    }
  }

Setup (Claude Code):  claude mcp add ed-sentinel -- python /path/to/mcp_server.py

Then in conversation:
  "Run a full site check"
  "Check /pricing right now — I just published an edit"
  "Are AI crawlers still allowed?"
  "What changed on the homepage since last night?"
  "Show me this week's social drafts"  (then: "schedule them via OneUp")
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

import sentinel as S
from checks_ext import run_security_suite

ROOT = Path(__file__).resolve().parent
mcp = FastMCP("ed-sentinel")


def _contract() -> dict:
    return yaml.safe_load((ROOT / "site_contract.yaml").read_text())


def _fetcher(contract: dict) -> S.Fetcher:
    return S.Fetcher(contract["site"].get("user_agent", "EnormousDoorSentinel/1.0"))


def _fmt(findings) -> str:
    if not findings:
        return "All checks passed. 🟢"
    lines = []
    for sev in (S.FAIL, S.WARN, S.INFO):
        group = [f for f in findings if f.severity == sev]
        if group:
            lines.append(f"\n{sev} ({len(group)}):")
            lines += [f"  • {f.page} · {f.check} — {f.message}"
                      + (f"\n      {f.evidence[:300]}" if f.evidence else "")
                      for f in group]
    return "\n".join(lines).strip()


@mcp.tool()
def run_full_check(confirm: bool = True) -> str:
    """Run the complete sentinel suite against the LIVE site right now:
    all pages, routing, pricing (table+estimator+JSON-LD), schema
    guardrails, robots/AI-crawler access, security, retired pages.
    Set confirm=False to skip the 45s confirmation re-fetch of failures
    (faster, but transient/cache failures won't be filtered)."""
    c = _contract()
    f = _fetcher(c)
    findings, _ = S.run_checks(f, c)
    if confirm and any(x.severity == S.FAIL for x in findings):
        findings, transient = S.confirm_failures(
            f, c, findings, c["site"].get("confirm_delay_seconds", 45))
        note = f"\n({len(transient)} transient failure(s) filtered by confirmation re-fetch)" if transient else ""
    else:
        note = ""
    fails = sum(1 for x in findings if x.severity == S.FAIL)
    head = f"{'🔴 ' + str(fails) + ' confirmed issue(s)' if fails else '🟢 CLEAN'} across {len(c['pages'])} pages."
    return head + note + "\n\n" + _fmt(findings)


@mcp.tool()
def check_page(path: str) -> str:
    """Check ONE page live against its contract entry (e.g. '/pricing').
    Use immediately after publishing an edit to verify it took."""
    c = _contract()
    spec = next((p for p in c["pages"] if p["path"] == path), None)
    if spec is None:
        return (f"{path} is not in the contract. Monitored pages: "
                + ", ".join(p["path"] for p in c["pages"]))
    snap = S.fetch_snapshot(_fetcher(c), c, path)
    findings = S.check_page(snap, spec)
    findings += S.check_global_jsonld(
        {path: snap}, c.get("jsonld_global", {}).get("forbidden_types", []) or [])
    head = (f"{path} — status {snap.status}, {snap.elapsed_ms} ms\n"
            f"title: {snap.title!r}\nH1: {snap.h1s}\n")
    return head + "\n" + _fmt(findings)


@mcp.tool()
def check_crawler_access() -> str:
    """Verify robots.txt allows Google, Bing, and every AI crawler
    (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, …) on all
    monitored pages. The check that catches invisibility regressions."""
    c = _contract()
    findings, robots_body = S.check_robots(_fetcher(c), c)
    head = "🟢 all enforced crawlers allowed on all monitored pages." \
        if not any(x.severity == S.FAIL for x in findings) else "🔴 crawler access problem:"
    return head + "\n\n" + _fmt(findings) + \
        (f"\n\nrobots.txt:\n{robots_body[:800]}" if robots_body else "")


@mcp.tool()
def check_security() -> str:
    """Run the security suite live: SSL expiry, mixed content, security
    headers, response-time budget, conversion-critical external links."""
    c = _contract()
    f = _fetcher(c)
    snaps = {p["path"]: S.fetch_snapshot(f, c, p["path"]) for p in c["pages"]}
    return _fmt(run_security_suite(f, c, snaps)) or "🟢 security suite clean."


@mcp.tool()
def verify_pricing() -> str:
    """Live-verify pricing in all three locations at once: visible table,
    estimator JavaScript, and JSON-LD Service schema — plus the stale
    $520/$620 tripwires. Run after any pricing edit."""
    c = _contract()
    spec = next(p for p in c["pages"] if p["path"] == "/pricing")
    snap = S.fetch_snapshot(_fetcher(c), c, "/pricing")
    findings = S.check_page(snap, spec)
    price_findings = [x for x in findings if x.check in
                      ("required_pattern", "forbidden_pattern", "estimator",
                       "jsonld_price", "jsonld_stale_price", "jsonld_count")]
    return (f"JSON-LD prices found: {sorted(set(snap.jsonld_prices))}\n\n"
            + (_fmt(price_findings) or "🟢 pricing consistent in all three locations."))


@mcp.tool()
def diff_page(path: str) -> str:
    """Show what changed on a page vs. the sentinel's stored baseline
    (from the last nightly run)."""
    c = _contract()
    slug = path.strip("/").replace("/", "_") or "home"
    stored = ROOT / "state" / "pages" / f"{slug}.txt"
    if not stored.exists():
        return f"No baseline stored yet for {path} — run the nightly workflow once first."
    snap = S.fetch_snapshot(_fetcher(c), c, path)
    if snap.status != 200:
        return f"{path} returned status {snap.status}."
    old = stored.read_text()
    if old == snap.text:
        return f"{path}: no changes vs. baseline."
    diff = "\n".join(list(difflib.unified_diff(
        old.split(". "), snap.text.split(". "),
        "baseline", "live", lineterm=""))[:80])
    return f"{path} changed vs. baseline:\n\n{diff}"


@mcp.tool()
def get_status() -> str:
    """The living site-status document (STATUS.md) from the last run."""
    p = ROOT / "STATUS.md"
    return p.read_text() if p.exists() else "STATUS.md not generated yet — run the workflow once."


@mcp.tool()
def get_latest_report() -> str:
    """Full report from the most recent sentinel run."""
    p = ROOT / "reports" / "latest.md"
    return p.read_text() if p.exists() else "No report yet — run the workflow once."


@mcp.tool()
def get_visibility_trend() -> str:
    """AI-answer share-of-voice: latest panel report plus the raw
    trendline CSV tail. Shows which buyer questions mention the brand."""
    rep = ROOT / "reports" / "visibility.md"
    csv_p = ROOT / "state" / "visibility.csv"
    out = rep.read_text() if rep.exists() else "No visibility panel has run yet."
    if csv_p.exists():
        lines = csv_p.read_text().splitlines()
        out += "\n\n--- trendline (last 30 rows) ---\n" + "\n".join(lines[-30:])
    return out


@mcp.tool()
def get_pending_social_drafts() -> str:
    """This week's social post drafts from the content engine — read
    these, then schedule them through the OneUp connector."""
    d = ROOT / "social-drafts"
    files = sorted(d.glob("*.md")) if d.exists() else []
    if not files:
        return "No social drafts yet — the weekly content engine hasn't produced any."
    return files[-1].read_text()


@mcp.tool()
def get_content_drafts(latest_only: bool = True) -> str:
    """Page draft(s) from the content engine, paste-ready for Squarespace
    (SEO title, description, slug, H1, body)."""
    d = ROOT / "content-drafts"
    files = sorted(d.glob("*.md")) if d.exists() else []
    if not files:
        return "No content drafts yet — the weekly content engine hasn't produced any."
    if latest_only:
        return files[-1].read_text()
    return "\n\n".join(f"===== {f.name} =====\n{f.read_text()}" for f in files[-4:])


@mcp.tool()
def list_monitored_pages() -> str:
    """Every page in the contract with its enforced H1 and requirements."""
    c = _contract()
    lines = []
    for p in c["pages"]:
        req = len(p.get("required_links") or []) + len(p.get("required_patterns") or [])
        lines.append(f"• {p['path']} — H1: {p.get('h1') or '(captured)'}"
                     f" — {req} explicit requirement(s)")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
