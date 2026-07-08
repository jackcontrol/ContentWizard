#!/usr/bin/env python3
"""
Offline self-test for the sentinel engine.

Runs the full check pipeline against local HTML fixtures via the
Fetcher's fixture_map — no network required. Two scenarios:

  GOOD site  -> zero FAIL findings expected
  BAD  site  -> a specific set of check IDs MUST fire
                (stale prices in table/estimator/JSON-LD, dropped
                #mix-prep anchor, double H1, legacy title, forbidden
                Review schema, robots blocking /technical-faq and
                GPTBot sitewide, retired /test resurrected)

Usage:  python tests/run_self_test.py     (from repo root)
Exit 0 = all assertions pass.
"""

import json
import yaml
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentinel import (Fetcher, run_checks, check_robots, FAIL)  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
BASE = "https://enormousdoor.com"

# A trimmed contract targeting just the pages we have fixtures for.
# Defined as a plain dict (raw strings) so regexes carry no extra
# escaping layers — this mirrors what yaml.safe_load produces from
# the real single-quoted contract file.
TEST_CONTRACT = {
    "site": {
        "canonical_base": BASE,
        "internal_hosts": ["enormousdoor.com", "www.enormousdoor.com"],
        "sitemap_url": f"{BASE}/sitemap.xml",
        "confirm_delay_seconds": 0,
        "user_agent": "SentinelSelfTest/1.0",
    },
    "robots": {
        "agents_must_allow": ["*", "Googlebot", "GPTBot", "ClaudeBot"],
        "agents_warn_if_blocked": ["CCBot"],
    },
    "jsonld_global": {"forbidden_types": ["Review", "AggregateRating", "VideoObject"]},
    "retired_pages": [{"path": "/test"}],
    "pages": [
        {
            "path": "/pricing",
            "title_contains": "Heavy Music Mastering Pricing | Enormous Door Mastering",
            "h1": "HEAVY MUSIC MASTERING PRICING",
            "required_links": ["/launch-contact", "/technical-faq#mix-prep"],
            "required_patterns": [r"\$500", r"\$600", r"\$850", r"\$150", r"\$1500"],
            "forbidden_patterns": [r"\$520", r"\$620"],
            "estimator_patterns": [
                r"lp45[\s\S]{0,120}?singleformat\s*:\s*500",
                r"lp45[\s\S]{0,120}?full\s*:\s*600",
            ],
            "jsonld": {
                "types_expected": ["WebPage", "Organization", "LocalBusiness",
                                   "BreadcrumbList", "WebSite", "Service", "FAQPage"],
                "type_counts": {"Service": 2},
                "prices_required": ["500", "600", "850"],
                "prices_forbidden": ["520", "620"],
            },
        },
        {
            "path": "/technical-faq",
            "title_contains": "Mix Prep for Mastering | Heavy Music Mastering Specs",
            "h1": "MIX PREP & DELIVERY SPECS",
            "required_links": ["/launch-contact", "/pricing",
                               "https://enormousdoor.wetransfer.com"],
            "anchor_ids_required": ["mix-prep"],
        },
    ],
    "cross_page": {"unique_h1": True, "warn_canonical_host": "enormousdoor.com"},
}


def fixture_fetcher(mapping: dict) -> Fetcher:
    return Fetcher("SentinelSelfTest/1.0", fixture_map=mapping)


def fails_of(findings):
    return {(f.page, f.check) for f in findings if f.severity == FAIL}


def scenario_good():
    mapping = {
        f"{BASE}/pricing": (200, FIX / "good_pricing.html"),
        f"{BASE}/technical-faq": (200, FIX / "technical_faq.html"),
        f"{BASE}/robots.txt": (200, FIX / "robots_good.txt"),
        f"{BASE}/sitemap.xml": (200, FIX / "sitemap.xml"),
        f"{BASE}/test": (404, ""),
    }
    findings, _ = run_checks(fixture_fetcher(mapping), TEST_CONTRACT)
    bad = fails_of(findings)
    assert not bad, f"GOOD scenario should be clean, got FAILs: {sorted(bad)}"
    print(f"  GOOD scenario: clean ({len(findings)} non-fail findings) ✔")


def scenario_bad():
    mapping = {
        f"{BASE}/pricing": (200, FIX / "bad_pricing.html"),
        f"{BASE}/technical-faq": (200, FIX / "technical_faq_noanchor.html"),
        f"{BASE}/robots.txt": (200, FIX / "robots_bad.txt"),
        f"{BASE}/sitemap.xml": (200, FIX / "sitemap.xml"),
        f"{BASE}/test": (200, "<html><body>zombie test page</body></html>"),
    }
    findings, _ = run_checks(fixture_fetcher(mapping), TEST_CONTRACT)
    bad = fails_of(findings)

    must_fire = {
        ("/pricing", "title"),                 # legacy SEO title
        ("/pricing", "h1_count"),              # two H1s
        ("/pricing", "required_link"),         # anchor dropped -> bare /technical-faq
        ("/pricing", "forbidden_pattern"),     # $520 / $620 in visible table
        ("/pricing", "estimator"),             # stale estimator JS values
        ("/pricing", "jsonld_price"),          # 500/600 missing from schema
        ("/pricing", "jsonld_stale_price"),    # 520/620 present in schema
        ("/pricing", "jsonld_forbidden_type"), # Review schema guardrail
        ("/technical-faq", "anchor_target"),   # id="mix-prep" missing
        ("/technical-faq", "robots_blocked"),  # Disallow: /technical-faq
        ("/pricing", "robots_blocked"),        # GPTBot blocked sitewide
        ("/test", "retired_alive"),            # zombie page
    }
    missing = must_fire - bad
    assert not missing, f"BAD scenario failed to detect: {sorted(missing)}\nDetected: {sorted(bad)}"
    print(f"  BAD scenario: all {len(must_fire)} expected detections fired "
          f"({len(bad)} total FAILs) ✔")


def scenario_robots_direct():
    """robots parser sanity: exact agent groups honored."""
    mapping = {f"{BASE}/robots.txt": (200, FIX / "robots_bad.txt")}
    findings, _ = check_robots(fixture_fetcher(mapping), TEST_CONTRACT)
    keys = fails_of(findings)
    assert ("/technical-faq", "robots_blocked") in keys
    assert any(p == "/pricing" and c == "robots_blocked" for p, c in keys), \
        "GPTBot sitewide block not detected"
    print("  robots parsing: agent-specific and path-specific blocks detected ✔")


def render_conforming_page(spec: dict, path: str) -> str:
    """Generate minimal HTML that satisfies a contract page spec.
    Used to validate the REAL site_contract.yaml end-to-end offline:
    if the generator + contract disagree, the contract has a typo."""
    title = spec.get("title_contains") or f"Page {path}"
    h1 = spec.get("h1") or f"PAGE {path.upper()}"
    links = "".join(f'<a href="{t}">link</a>' for t in (spec.get("required_links") or []))
    anchors = "".join(f'<div id="{a}">anchor</div>'
                      for a in (spec.get("anchor_ids_required") or []))

    # Satisfy literal-ish required patterns (our contract uses \$NNN):
    pat_text = " ".join(p.replace("\\", "")
                        for p in (spec.get("required_patterns") or []))
    estim = ""
    if spec.get("estimator_patterns"):
        estim = "<script>var p={lp45:{singleformat: 500, full: 600}};</script>"

    jl = spec.get("jsonld") or {}
    graph = []
    counts = dict(jl.get("type_counts") or {})
    for t in jl.get("types_expected") or []:
        n = counts.get(t, 1)
        for _ in range(n):
            node = {"@type": t}
            if t == "Service" and jl.get("prices_required"):
                node["offers"] = [{"@type": "Offer", "price": pr, "priceCurrency": "USD"}
                                  for pr in jl["prices_required"]]
            graph.append(node)
    jl_script = (f'<script type="application/ld+json">'
                 f'{json.dumps({"@graph": graph})}</script>') if graph else ""

    return (f"<html><head><title>{title} — ENORMOUS DOOR MASTERING</title>"
            f'<link rel="canonical" href="https://enormousdoor.com{path}">'
            f"{jl_script}</head><body><h1>{h1}</h1>{anchors}{links}"
            f"<p>{pat_text}</p>{estim}</body></html>")


def scenario_full_contract():
    """The REAL site_contract.yaml must validate clean against pages
    generated to satisfy it — catches contract typos/regex mistakes."""
    contract = yaml.safe_load((ROOT / "site_contract.yaml").read_text())
    contract["site"]["confirm_delay_seconds"] = 0
    base = contract["site"]["canonical_base"]
    mapping = {
        f"{base}/robots.txt": (200, FIX / "robots_good.txt"),
        f"{base}/sitemap.xml": (200, "<urlset>" + "".join(
            f"<url><loc>{base}{p['path']}</loc></url>" for p in contract["pages"]
        ) + f"<url><loc>{base}/</loc></url></urlset>"),
    }
    for entry in contract.get("retired_pages") or []:
        mapping[base + entry["path"]] = (404, "")
    for spec in contract["pages"]:
        mapping[base + spec["path"]] = (200, render_conforming_page(spec, spec["path"]))
    # External conversion links (security suite):
    for e in (contract.get("security", {}).get("external_links_must_resolve") or []):
        url = e if isinstance(e, str) else e["url"]
        mapping[url] = (200, "ok")

    findings, _ = run_checks(Fetcher("t", fixture_map=mapping), contract)
    bad = fails_of(findings)
    assert not bad, f"real contract has internal inconsistencies: {sorted(bad)}"
    print(f"  FULL real contract: {len(contract['pages'])} pages validate clean ✔")


def scenario_security():
    """Mixed content FAILs; dead WeTransfer link FAILs; dead soft link
    WARNs only; missing HSTS header WARNs."""
    from checks_ext import run_security_suite
    contract = {
        "site": {"canonical_base": BASE,
                 "internal_hosts": ["enormousdoor.com"],
                 "confirm_delay_seconds": 0, "user_agent": "t"},
        "security": {
            "required_headers_warn": ["strict-transport-security"],
            "response_time_warn_ms": 1,   # fixtures report 0 ms -> no warn
            "external_links_must_resolve": [
                {"url": "https://enormousdoor.wetransfer.com/", "fail": True},
                "https://heliospressing.com",
            ],
        },
        "pages": [{"path": "/x"}],
    }
    mixed = ('<html><head><title>x</title></head><body><h1>X</h1>'
             '<img src="http://cdn.example.com/pic.jpg"></body></html>')
    mapping = {
        f"{BASE}/x": (200, mixed),
        "https://enormousdoor.wetransfer.com/": (503, ""),
        "https://heliospressing.com": (404, ""),
    }
    f = Fetcher("t", fixture_map=mapping)
    from sentinel import fetch_snapshot
    snaps = {"/x": fetch_snapshot(f, contract, "/x")}
    findings = run_security_suite(f, contract, snaps)
    keys = {(x.page, x.check, x.severity) for x in findings}
    assert ("/x", "mixed_content", "FAIL") in keys
    assert ("GLOBAL", "external_link", "FAIL") in keys, "wetransfer hard-fail missing"
    assert ("GLOBAL", "external_link", "WARN") in keys, "soft external warn missing"
    assert ("/x", "security_header", "WARN") in keys
    print("  security suite: mixed content, HSTS, hard/soft external links ✔")


def scenario_defacement():
    """A drastic single-run rewrite must raise a FAIL, a small edit only INFO."""
    import tempfile, shutil
    from sentinel import update_state_and_diffs, PageSnapshot
    contract = {"security": {"drastic_change_fail_pct": 60}}
    tmp = Path(tempfile.mkdtemp())
    (tmp / "state").mkdir()

    def snap(text):
        s = PageSnapshot(path="/x", status=200)
        s.text = text
        import hashlib
        s.text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        s.title, s.h1s = "t", ["X"]
        return s

    state = {"pages": {}, "runs": 0}
    update_state_and_diffs(tmp, state, {"/x": snap("heavy music mastering " * 40)}, contract)
    small = update_state_and_diffs(tmp, state,
                                   {"/x": snap("heavy music mastering " * 39 + "vinyl ")}, contract)
    assert not any(x.check == "drastic_content_change" for x in small)
    big = update_state_and_diffs(tmp, state,
                                 {"/x": snap("BUY CHEAP PILLS " * 40)}, contract)
    assert any(x.check == "drastic_content_change" and x.severity == FAIL for x in big)
    shutil.rmtree(tmp)
    print("  defacement alarm: fires on drastic rewrite, silent on small edit ✔")


if __name__ == "__main__":
    print("Sentinel self-test")
    scenario_good()
    scenario_bad()
    scenario_robots_direct()
    scenario_full_contract()
    scenario_security()
    scenario_defacement()
    print("ALL SELF-TESTS PASSED")
