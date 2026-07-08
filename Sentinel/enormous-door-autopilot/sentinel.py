#!/usr/bin/env python3
"""
Enormous Door Site Sentinel
===========================
Nightly watchdog that checks the live site against site_contract.yaml.

Design principles (learned the hard way during the July 2026 audit):
  * CACHE-PROOF: every fetch sends no-cache headers AND a unique
    cache-busting query parameter, so stale CDN/edge copies can't
    produce false positives.
  * DOUBLE CONFIRMATION: any failing check triggers a fresh re-fetch
    after a delay; only failures that persist are reported. The
    sentinel never cries wolf on a transient.
  * DETECT, DON'T TOUCH: the sentinel never modifies the site. It
    reports. Search Console indexing requests remain a human action.
  * LIVING HANDOFF: STATUS.md is regenerated every run and replaces
    the manually-maintained handoff document.

Outputs (relative to repo root):
  STATUS.md            — living state document (always regenerated)
  reports/latest.md    — full report of the most recent run
  reports/history.log  — one line per run
  state/observed.json  — baseline: hashes, captured H1s/titles, streaks
  state/pages/*.txt    — extracted text per page (for diffs)
  alert.md             — created ONLY when confirmed failures exist
                         (the GitHub workflow keys alerting off this file)

Exit code is always 0; use --fail-on-alert to exit 1 when alert.md
is written (useful for local runs).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse, urljoin

import requests
import yaml
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Severity levels
# ----------------------------------------------------------------------
FAIL = "FAIL"   # contract violation -> alert (after confirmation)
WARN = "WARN"   # worth knowing, never alerts by itself
INFO = "INFO"   # observational (e.g., content changed)
PASS = "PASS"


@dataclass
class Finding:
    severity: str
    page: str          # path or "GLOBAL"
    check: str         # short machine id, e.g. "h1_text"
    message: str
    evidence: str = ""

    def line(self) -> str:
        ev = f"\n        evidence: {self.evidence}" if self.evidence else ""
        return f"[{self.severity}] {self.page} :: {self.check} — {self.message}{ev}"


@dataclass
class PageSnapshot:
    path: str
    status: int = 0
    final_url: str = ""
    html: str = ""
    text: str = ""
    text_hash: str = ""
    title: str = ""
    h1s: list = field(default_factory=list)
    links: list = field(default_factory=list)   # normalized hrefs
    jsonld_types: list = field(default_factory=list)
    jsonld_prices: list = field(default_factory=list)
    noindex: bool = False
    canonical: str = ""
    fetch_error: str = ""
    resp_headers: dict = field(default_factory=dict)
    elapsed_ms: int = 0


# ----------------------------------------------------------------------
# Fetching (cache-proof)
# ----------------------------------------------------------------------
class Fetcher:
    """HTTP fetcher with no-cache headers + cache-busting query param.

    In tests, `fixture_map` maps full URLs -> (status, filepath|text)
    so the whole engine runs offline against fixtures.
    """

    def __init__(self, user_agent: str, fixture_map: dict | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.fixture_map = fixture_map

    def get(self, url: str, bust: bool = True, timeout: int = 30):
        """Return (status_code, text, final_url, headers). Never raises.
        headers carries a synthetic "__elapsed_ms__" entry for timing."""
        if self.fixture_map is not None:
            entry = self.fixture_map.get(url)
            if entry is None:
                return 404, "", url, {"__elapsed_ms__": "0"}
            status, payload = entry
            text = Path(payload).read_text(encoding="utf-8") if isinstance(payload, Path) else payload
            return status, text, url, {"__elapsed_ms__": "0"}
        target = url
        if bust:
            sep = "&" if "?" in url else "?"
            target = f"{url}{sep}sv={int(time.time() * 1000)}"
        try:
            t0 = time.time()
            r = self.session.get(target, timeout=timeout, allow_redirects=True)
            headers = dict(r.headers)
            headers["__elapsed_ms__"] = str(int((time.time() - t0) * 1000))
            return r.status_code, r.text, r.url, headers
        except requests.RequestException as exc:
            return 0, "", url, {"__error__": str(exc), "__elapsed_ms__": "0"}


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------
def norm_ws(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip()


def normalize_href(href: str, base_url: str, internal_hosts: list[str]) -> str:
    """Absolute-ify then strip scheme+host for internal links,
    preserving the #fragment (anchors matter to us). Strips the
    sentinel's own cache-buster if it ever leaks into a link."""
    if not href:
        return ""
    absolute = urljoin(base_url, href.strip())
    p = urlparse(absolute)
    if p.netloc.lower() in internal_hosts:
        path = p.path.rstrip("/") or "/"
        frag = f"#{p.fragment}" if p.fragment else ""
        return f"{path}{frag}"
    return absolute.split("?sv=")[0]


def collect_jsonld_types(node, out: list):
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(x for x in t if isinstance(x, str))
        for v in node.values():
            collect_jsonld_types(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_jsonld_types(v, out)


PRICE_KEYS = {"price", "lowprice", "highprice", "minprice", "maxprice"}


def collect_jsonld_prices(node, out: list):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in PRICE_KEYS and isinstance(v, (str, int, float)):
                out.append(str(v).strip())
            else:
                collect_jsonld_prices(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_jsonld_prices(v, out)


def parse_page(path: str, status: int, html: str, final_url: str,
               headers: dict, base_url: str, internal_hosts: list[str]) -> PageSnapshot:
    snap = PageSnapshot(path=path, status=status, final_url=final_url, html=html)
    snap.resp_headers = {k.lower(): v for k, v in headers.items()}
    try:
        snap.elapsed_ms = int(headers.get("__elapsed_ms__", 0) or 0)
    except (TypeError, ValueError):
        snap.elapsed_ms = 0
    if "__error__" in headers:
        snap.fetch_error = headers["__error__"]
    if not html:
        return snap
    soup = BeautifulSoup(html, "html.parser")

    snap.title = norm_ws(soup.title.get_text()) if soup.title else ""
    snap.h1s = [norm_ws(h.get_text()) for h in soup.find_all("h1")]
    snap.links = sorted({
        normalize_href(a.get("href", ""), base_url + path, internal_hosts)
        for a in soup.find_all("a") if a.get("href")
    })

    # meta robots noindex (header X-Robots-Tag too)
    robots_meta = " ".join(
        (m.get("content") or "") for m in soup.find_all("meta", attrs={"name": re.compile("^robots$", re.I)})
    )
    xrt = headers.get("X-Robots-Tag", "") or headers.get("x-robots-tag", "")
    snap.noindex = "noindex" in (robots_meta + " " + xrt).lower()

    link_canon = soup.find("link", rel=lambda v: v and "canonical" in v)
    snap.canonical = (link_canon.get("href") or "").strip() if link_canon else ""

    for script in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        raw = script.string or script.get_text() or ""
        raw = raw.strip().strip("\ufeff")
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:  # tolerate stray control chars Squarespace sometimes emits
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except json.JSONDecodeError:
                continue
        collect_jsonld_types(data, snap.jsonld_types)
        collect_jsonld_prices(data, snap.jsonld_prices)

    # Visible-text extraction for change detection (scripts/styles removed)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    snap.text = norm_ws(soup.get_text(" "))
    snap.text_hash = hashlib.sha256(snap.text.encode("utf-8")).hexdigest()[:16]
    return snap


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------
def check_page(snap: PageSnapshot, spec: dict) -> list[Finding]:
    f: list[Finding] = []
    p = snap.path

    if snap.fetch_error:
        f.append(Finding(FAIL, p, "fetch", f"request failed: {snap.fetch_error}"))
        return f
    if snap.status != 200:
        f.append(Finding(FAIL, p, "http_status", f"expected 200, got {snap.status}"))
        return f

    if snap.noindex and not spec.get("noindex_allowed"):
        f.append(Finding(FAIL, p, "noindex", "page is served with a noindex directive"))

    # ---- title / h1 ----
    tc = spec.get("title_contains")
    if tc and norm_ws(tc).lower() not in snap.title.lower():
        f.append(Finding(FAIL, p, "title", f"<title> missing expected text",
                         evidence=f"expected to contain: {tc!r} | got: {snap.title!r}"))

    h1_expected = spec.get("h1", "__unset__")
    if len(snap.h1s) != 1:
        f.append(Finding(FAIL, p, "h1_count",
                         f"expected exactly 1 <h1>, found {len(snap.h1s)}",
                         evidence="; ".join(snap.h1s[:4])))
    elif h1_expected not in ("__unset__", None):
        if norm_ws(h1_expected).lower() != snap.h1s[0].lower():
            f.append(Finding(FAIL, p, "h1_text", "H1 text does not match contract",
                             evidence=f"expected: {h1_expected!r} | got: {snap.h1s[0]!r}"))

    # ---- required links (fragment-aware) ----
    for target in spec.get("required_links", []) or []:
        if target.startswith("http"):
            ok = any(l.startswith(target) for l in snap.links)
        else:
            ok = target in snap.links
        if not ok:
            hint = ""
            if "#" in target:
                bare = target.split("#")[0]
                if bare in snap.links:
                    hint = f"(bare {bare} exists — anchor was dropped; in Squarespace, paste the full path into the URL field rather than picking the page from the dropdown)"
            f.append(Finding(FAIL, p, "required_link",
                             f"no <a> pointing to {target} {hint}".strip()))

    # ---- raw-HTML patterns ----
    for pat in spec.get("required_patterns", []) or []:
        if not re.search(pat, snap.html):
            f.append(Finding(FAIL, p, "required_pattern", f"pattern not found: {pat!r}"))
    for pat in spec.get("forbidden_patterns", []) or []:
        m = re.search(pat, snap.html)
        if m:
            f.append(Finding(FAIL, p, "forbidden_pattern",
                             f"stale/forbidden pattern present: {pat!r}",
                             evidence=snap.html[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")))
    for pat in spec.get("estimator_patterns", []) or []:
        if not re.search(pat, snap.html):
            f.append(Finding(FAIL, p, "estimator", f"estimator JS check failed: {pat!r}"))

    # ---- anchor targets ----
    for anchor in spec.get("anchor_ids_required", []) or []:
        if not re.search(rf'''(?:id|name)\s*=\s*["']{re.escape(anchor)}["']''', snap.html):
            f.append(Finding(FAIL, p, "anchor_target",
                             f'no element with id="{anchor}" — sitewide #{anchor} links will not jump'))

    # ---- JSON-LD ----
    jl = spec.get("jsonld") or {}
    types = snap.jsonld_types
    for t in jl.get("types_expected", []) or []:
        if t not in types:
            f.append(Finding(FAIL, p, "jsonld_type", f"expected JSON-LD @type {t} not found",
                             evidence=f"found: {sorted(set(types))}"))
    for t, n in (jl.get("type_counts") or {}).items():
        got = types.count(t)
        if got != n:
            f.append(Finding(FAIL, p, "jsonld_count", f"expected {n}× @type {t}, found {got}"))
    for price in jl.get("prices_required", []) or []:
        if str(price) not in snap.jsonld_prices:
            f.append(Finding(FAIL, p, "jsonld_price", f"price {price} missing from JSON-LD",
                             evidence=f"prices found: {sorted(set(snap.jsonld_prices))}"))
    for price in jl.get("prices_forbidden", []) or []:
        if str(price) in snap.jsonld_prices:
            f.append(Finding(FAIL, p, "jsonld_stale_price",
                             f"STALE price {price} still present in JSON-LD"))
    return f


def check_global_jsonld(snaps: dict[str, PageSnapshot], forbidden: list[str]) -> list[Finding]:
    out = []
    for path, snap in snaps.items():
        for t in forbidden:
            if t in snap.jsonld_types:
                out.append(Finding(FAIL, path, "jsonld_forbidden_type",
                                   f"guardrail: forbidden schema type {t} detected"))
    return out


def check_unique_h1(snaps: dict[str, PageSnapshot]) -> list[Finding]:
    seen: dict[str, str] = {}
    out = []
    for path, snap in snaps.items():
        if len(snap.h1s) == 1:
            key = snap.h1s[0].lower()
            if key in seen:
                out.append(Finding(FAIL, path, "h1_duplicate",
                                   f"H1 {snap.h1s[0]!r} duplicates {seen[key]} (keyword cannibalization)"))
            else:
                seen[key] = path
    return out


def check_canonicals(snaps: dict[str, PageSnapshot], host: str) -> list[Finding]:
    out = []
    for path, snap in snaps.items():
        if snap.canonical:
            netloc = urlparse(snap.canonical).netloc.lower()
            if netloc and netloc != host:
                out.append(Finding(WARN, path, "canonical_host",
                                   f"canonical points at {netloc}, expected {host}",
                                   evidence=snap.canonical))
    return out


def check_robots(fetcher: Fetcher, contract: dict) -> tuple[list[Finding], str]:
    base = contract["site"]["canonical_base"]
    robots_url = f"{base}/robots.txt"
    status, body, _, headers = fetcher.get(robots_url, bust=False)
    out: list[Finding] = []
    if status != 200 or not body:
        out.append(Finding(WARN, "GLOBAL", "robots_missing",
                           f"robots.txt not readable (status {status}) — crawlers default to allow"))
        return out, ""

    rp = robotparser.RobotFileParser()
    rp.parse(body.splitlines())

    paths = [p["path"] for p in contract["pages"]]
    for agent in contract.get("robots", {}).get("agents_must_allow", []) or []:
        for path in paths:
            if not rp.can_fetch(agent, base + path):
                out.append(Finding(FAIL, path, "robots_blocked",
                                   f"robots.txt blocks user-agent {agent!r} — page invisible to that crawler"))
    for agent in contract.get("robots", {}).get("agents_warn_if_blocked", []) or []:
        blocked = [p for p in paths if not rp.can_fetch(agent, base + p)]
        if blocked:
            out.append(Finding(WARN, "GLOBAL", "robots_optional_agent",
                               f"user-agent {agent!r} blocked on {len(blocked)} page(s) — confirm intentional"))
    if "sitemap" not in body.lower():
        out.append(Finding(WARN, "GLOBAL", "robots_sitemap",
                           "robots.txt has no Sitemap: directive"))
    return out, body


def check_sitemap(fetcher: Fetcher, contract: dict) -> list[Finding]:
    url = contract["site"].get("sitemap_url")
    if not url:
        return []
    status, body, _, _ = fetcher.get(url, bust=False)
    if status != 200 or not body:
        return [Finding(WARN, "GLOBAL", "sitemap_fetch", f"sitemap not readable (status {status})")]
    out = []
    base = contract["site"]["canonical_base"]
    for page in contract["pages"]:
        path = page["path"]
        variants = {base + path, base + path + "/",
                    base.replace("://", "://www.") + path,
                    base.replace("://", "://www.") + path + "/"}
        if path == "/":
            variants |= {base, base + "/"}
        if not any(v in body for v in variants):
            out.append(Finding(WARN, path, "sitemap_missing", "page not listed in sitemap.xml"))
    return out


def check_retired(fetcher: Fetcher, contract: dict) -> list[Finding]:
    base = contract["site"]["canonical_base"]
    out = []
    for entry in contract.get("retired_pages", []) or []:
        path = entry["path"]
        # No redirects followed: we want the *original* URL's own answer.
        if fetcher.fixture_map is not None:
            status, _, _, _ = fetcher.get(base + path, bust=False)
        else:
            try:
                r = fetcher.session.get(base + path, timeout=30, allow_redirects=False)
                status = r.status_code
            except requests.RequestException as exc:
                out.append(Finding(WARN, path, "retired_fetch", f"could not verify: {exc}"))
                continue
        if status == 200:
            out.append(Finding(FAIL, path, "retired_alive",
                               "retired page is serving 200 again — should be 301/404/410"))
    return out


# ----------------------------------------------------------------------
# Engine: fetch all, check all, confirm failures, persist, report
# ----------------------------------------------------------------------
def fetch_snapshot(fetcher: Fetcher, contract: dict, path: str) -> PageSnapshot:
    base = contract["site"]["canonical_base"]
    hosts = [h.lower() for h in contract["site"]["internal_hosts"]]
    status, html, final_url, headers = fetcher.get(base + path)
    return parse_page(path, status, html, final_url, headers, base, hosts)


def run_checks(fetcher: Fetcher, contract: dict) -> tuple[list[Finding], dict[str, PageSnapshot]]:
    snaps: dict[str, PageSnapshot] = {}
    findings: list[Finding] = []
    for spec in contract["pages"]:
        snap = fetch_snapshot(fetcher, contract, spec["path"])
        snaps[spec["path"]] = snap
        findings += check_page(snap, spec)

    findings += check_global_jsonld(
        snaps, contract.get("jsonld_global", {}).get("forbidden_types", []) or [])
    if contract.get("cross_page", {}).get("unique_h1"):
        findings += check_unique_h1(snaps)
    warn_host = contract.get("cross_page", {}).get("warn_canonical_host")
    if warn_host:
        findings += check_canonicals(snaps, warn_host)

    rob_findings, _ = check_robots(fetcher, contract)
    findings += rob_findings
    findings += check_sitemap(fetcher, contract)
    findings += check_retired(fetcher, contract)

    # Deterministic security & conversion-integrity suite (checks_ext.py)
    if contract.get("security") is not None:
        from checks_ext import run_security_suite
        findings += run_security_suite(fetcher, contract, snaps)
    return findings, snaps


def confirm_failures(fetcher: Fetcher, contract: dict,
                     findings: list[Finding], delay: int) -> tuple[list[Finding], list[Finding]]:
    """Re-verify FAIL findings after `delay` seconds with fresh fetches.
    Returns (confirmed, transient)."""
    fails = [f for f in findings if f.severity == FAIL]
    others = [f for f in findings if f.severity != FAIL]
    if not fails:
        return findings, []
    if delay:
        time.sleep(delay)

    # Re-run only the affected scopes.
    affected_paths = {f.page for f in fails if f.page != "GLOBAL"}
    spec_by_path = {p["path"]: p for p in contract["pages"]}
    recheck: list[Finding] = []

    page_scoped = [f for f in fails if f.page in spec_by_path and f.check not in
                   ("robots_blocked", "retired_alive")]
    if page_scoped:
        fresh_snaps = {}
        for path in {f.page for f in page_scoped}:
            fresh_snaps[path] = fetch_snapshot(fetcher, contract, path)
            recheck += check_page(fresh_snaps[path], spec_by_path[path])
        recheck += check_global_jsonld(
            fresh_snaps, contract.get("jsonld_global", {}).get("forbidden_types", []) or [])

    if any(f.check == "robots_blocked" for f in fails):
        rf, _ = check_robots(fetcher, contract)
        recheck += rf
    if any(f.check == "retired_alive" for f in fails):
        recheck += check_retired(fetcher, contract)

    recheck_keys = {(f.page, f.check) for f in recheck if f.severity == FAIL}
    confirmed, transient = [], []
    for f in fails:
        (confirmed if (f.page, f.check) in recheck_keys else transient).append(f)
    for t in transient:
        others.append(Finding(INFO, t.page, t.check + "_transient",
                              f"failed once, passed on confirmation re-fetch (likely cache/transient): {t.message}"))
    return confirmed + others, transient


# ----------------------------------------------------------------------
# State, diffs, reports
# ----------------------------------------------------------------------
def load_state(root: Path) -> dict:
    p = root / "state" / "observed.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"pages": {}, "runs": 0}


def update_state_and_diffs(root: Path, state: dict,
                           snaps: dict[str, PageSnapshot],
                           contract: dict | None = None) -> list[Finding]:
    findings = []
    pages_dir = root / "state" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    drastic_pct = int(((contract or {}).get("security") or {})
                      .get("drastic_change_fail_pct", 0) or 0)
    for path, snap in snaps.items():
        slug = path.strip("/").replace("/", "_") or "home"
        rec = state["pages"].setdefault(path, {})
        txt_file = pages_dir / f"{slug}.txt"
        if snap.status == 200 and snap.text:
            if rec.get("text_hash") and rec["text_hash"] != snap.text_hash:
                old = txt_file.read_text() if txt_file.exists() else ""
                diff = "\n".join(list(difflib.unified_diff(
                    old.split(". "), snap.text.split(". "),
                    "previous", "current", lineterm=""))[:60])
                # Defacement alarm: a single-run rewrite of most of the page
                # is more likely compromise/accident than an edit.
                if drastic_pct and old:
                    similarity = difflib.SequenceMatcher(None, old, snap.text).quick_ratio()
                    changed_pct = int((1 - similarity) * 100)
                    if changed_pct >= drastic_pct:
                        findings.append(Finding(FAIL, path, "drastic_content_change",
                                                f"~{changed_pct}% of page text changed in one run "
                                                f"(threshold {drastic_pct}%) — possible defacement, "
                                                "hack, or accidental mass-edit; verify immediately",
                                                evidence=diff[:1500]))
                findings.append(Finding(INFO, path, "content_changed",
                                        f"page content changed (last change {rec.get('last_changed', 'unknown')} -> now)",
                                        evidence=diff[:2000]))
                rec["last_changed"] = now
            elif not rec.get("text_hash"):
                rec["last_changed"] = now
            rec["text_hash"] = snap.text_hash
            rec["title"] = snap.title
            rec["h1"] = snap.h1s[0] if len(snap.h1s) == 1 else " | ".join(snap.h1s)
            txt_file.write_text(snap.text)
        rec["last_checked"] = now
        rec["status"] = snap.status
    state["runs"] = state.get("runs", 0) + 1
    state["last_run"] = now
    return findings


def write_reports(root: Path, contract: dict, findings: list[Finding],
                  snaps: dict[str, PageSnapshot], state: dict) -> bool:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    confirmed = [f for f in findings if f.severity == FAIL]
    warns = [f for f in findings if f.severity == WARN]
    infos = [f for f in findings if f.severity == INFO]

    # ---- latest.md ----
    buf = io.StringIO()
    buf.write(f"# Sentinel run — {now}\n\n")
    buf.write(f"Result: **{'🔴 ' + str(len(confirmed)) + ' confirmed issue(s)' if confirmed else '🟢 CLEAN'}**"
              f" · {len(warns)} warning(s) · {len(infos)} note(s)\n\n")
    for group, title in ((confirmed, "Confirmed failures"), (warns, "Warnings"), (infos, "Notes")):
        if group:
            buf.write(f"## {title}\n\n")
            for f in group:
                buf.write(f"- `{f.page}` **{f.check}** — {f.message}\n")
                if f.evidence:
                    buf.write(f"  \n  ```\n  {f.evidence}\n  ```\n")
            buf.write("\n")
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "latest.md").write_text(buf.getvalue())
    with open(root / "reports" / "history.log", "a") as h:
        h.write(f"{now}  fails={len(confirmed)} warns={len(warns)} notes={len(infos)}\n")

    # ---- STATUS.md (the living handoff) ----
    s = io.StringIO()
    s.write("# Enormous Door — Live Site Status\n\n")
    s.write("*Auto-generated by the Site Sentinel. This file supersedes the manual "
            "handoff document: it reflects the actual live site as of the last run.*\n\n")
    s.write(f"**Last run:** {now} · **Run #{state.get('runs', 0)}** · "
            f"**Result:** {'🔴 ' + str(len(confirmed)) + ' issue(s) — see reports/latest.md' if confirmed else '🟢 all contract checks passing'}\n\n")
    s.write("| Page | H1 | Status | Last content change | Last checked |\n")
    s.write("|---|---|---|---|---|\n")
    for spec in contract["pages"]:
        path = spec["path"]
        rec = state["pages"].get(path, {})
        s.write(f"| `{path}` | {rec.get('h1', '—')} | {rec.get('status', '—')} "
                f"| {rec.get('last_changed', '—')} | {rec.get('last_checked', '—')} |\n")
    s.write("\n## Standing guardrails (enforced nightly)\n\n"
            "Routing to `/launch-contact` and `/technical-faq#mix-prep`; pricing "
            "correct in visible table, estimator JS, and JSON-LD (stale $520/$620 "
            "tripwires armed); forbidden schema types (Review, AggregateRating, "
            "VideoObject) absent; one unique H1 per page; AI crawlers "
            "(GPTBot, ClaudeBot, PerplexityBot, Google-Extended, …) not blocked in "
            "robots.txt; retired pages (/test, /faqs) stay dead.\n\n"
            "*Manual-only actions (never automated, per guardrails): Search Console "
            "indexing requests; any edits to the site itself.*\n")
    (root / "STATUS.md").write_text(s.getvalue())

    # ---- alert.md (only on confirmed failures) ----
    alert_path = root / "alert.md"
    if confirmed:
        a = io.StringIO()
        a.write(f"## 🔴 Site Sentinel — {len(confirmed)} confirmed issue(s) · {now}\n\n")
        a.write("Each issue below failed an initial check **and** a fresh "
                "cache-busted re-fetch, so these are not cache ghosts.\n\n")
        for f in confirmed:
            a.write(f"- **`{f.page}`** · `{f.check}` — {f.message}\n")
            if f.evidence:
                a.write(f"  \n  ```\n  {f.evidence}\n  ```\n")
        a.write("\nFull report: `reports/latest.md`\n")
        alert_path.write_text(a.getvalue())
        return True
    if alert_path.exists():
        alert_path.unlink()
    return False


# ----------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enormous Door Site Sentinel")
    ap.add_argument("--contract", default="site_contract.yaml")
    ap.add_argument("--root", default=".", help="repo root for state/reports output")
    ap.add_argument("--confirm-delay", type=int, default=None,
                    help="override confirmation delay in seconds")
    ap.add_argument("--fail-on-alert", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    contract = yaml.safe_load(Path(args.contract).read_text())
    delay = args.confirm_delay if args.confirm_delay is not None \
        else contract["site"].get("confirm_delay_seconds", 45)

    fetcher = Fetcher(contract["site"].get("user_agent", "EnormousDoorSentinel/1.0"))
    print(f"Sentinel: checking {len(contract['pages'])} pages against contract…")
    findings, snaps = run_checks(fetcher, contract)

    n_fail = sum(1 for f in findings if f.severity == FAIL)
    if n_fail:
        print(f"{n_fail} failure(s) on first pass — confirming after {delay}s with fresh fetches…")
        findings, transient = confirm_failures(fetcher, contract, findings, delay)
        if transient:
            print(f"{len(transient)} failure(s) did not reproduce (cache/transient) — downgraded to notes.")

    state = load_state(root)
    findings += update_state_and_diffs(root, state, snaps, contract)
    (root / "state").mkdir(exist_ok=True)
    (root / "state" / "observed.json").write_text(json.dumps(state, indent=2))

    alerted = write_reports(root, contract, findings, snaps, state)
    for f in findings:
        print(f.line())
    print(f"\n{'ALERT written' if alerted else 'Clean run'} — see reports/latest.md and STATUS.md")
    return 1 if (alerted and args.fail_on_alert) else 0


if __name__ == "__main__":
    sys.exit(main())
