#!/usr/bin/env python3
"""
checks_ext.py — deterministic security & conversion-integrity checks.

All checks here are rule-based (no LLM, no API spend) and ride along
with the nightly sentinel run:

  * SSL certificate expiry            (FAIL when close to expiry)
  * Mixed content (http:// resources) (FAIL — breaks the padlock)
  * Security headers (HSTS)           (WARN — Squarespace-controlled)
  * Response-time budget              (WARN — slow pages kill conversion)
  * External conversion links alive   (WeTransfer = FAIL, others WARN)
  * Defacement alarm                  (FAIL on drastic single-run change;
                                       implemented in sentinel state layer,
                                       threshold defined in contract)
"""

from __future__ import annotations

import re
import socket
import ssl
from datetime import datetime, timezone

# Local import guard so this module works both as package and script.
try:
    from sentinel import Finding, FAIL, WARN, INFO  # type: ignore
except ImportError:  # pragma: no cover
    from .sentinel import Finding, FAIL, WARN, INFO  # type: ignore


MIXED_CONTENT_RE = re.compile(
    r'''(?:src|srcset|data-src)\s*=\s*["']http://'''
    r'''|<link[^>]+rel=["']?stylesheet["']?[^>]+href=["']http://''',
    re.I,
)


def check_page_security(snap, secconf: dict) -> list:
    """Per-page checks that need only the snapshot (offline-testable)."""
    out = []
    if snap.status != 200 or not snap.html:
        return out
    p = snap.path

    m = MIXED_CONTENT_RE.search(snap.html)
    if m:
        out.append(Finding(FAIL, p, "mixed_content",
                           "insecure http:// resource embedded on an https page",
                           evidence=snap.html[max(0, m.start() - 20):m.end() + 60].replace("\n", " ")))

    for header in secconf.get("required_headers_warn", []) or []:
        if header.lower() not in snap.resp_headers:
            out.append(Finding(WARN, p, "security_header",
                               f"response missing {header} header"))

    budget = int(secconf.get("response_time_warn_ms", 0) or 0)
    if budget and snap.elapsed_ms > budget:
        out.append(Finding(WARN, p, "slow_response",
                           f"page took {snap.elapsed_ms} ms (budget {budget} ms) — "
                           "slow pages depress both conversion and crawl priority"))
    return out


def check_ssl_expiry(contract: dict, offline: bool = False) -> list:
    """Certificate expiry for the canonical host. Skipped offline."""
    if offline:
        return []
    secconf = contract.get("security") or {}
    warn_days = int(secconf.get("ssl_expiry_warn_days", 21))
    host = contract["site"]["canonical_base"].split("://", 1)[-1].split("/")[0]
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (not_after - datetime.now(timezone.utc)).days
        if days <= 0:
            return [Finding(FAIL, "GLOBAL", "ssl_expired",
                            f"TLS certificate for {host} is EXPIRED")]
        if days <= warn_days:
            return [Finding(FAIL, "GLOBAL", "ssl_expiring",
                            f"TLS certificate for {host} expires in {days} day(s) — "
                            "Squarespace should auto-renew; investigate why it hasn't")]
        return [Finding(INFO, "GLOBAL", "ssl_ok",
                        f"TLS certificate valid for {days} more days")]
    except (ssl.SSLError, OSError, KeyError, ValueError) as exc:
        return [Finding(WARN, "GLOBAL", "ssl_check_error",
                        f"could not verify TLS certificate: {exc}")]


def check_external_links(fetcher, contract: dict) -> list:
    """Conversion-critical external links must resolve.
    Entries may be strings (WARN on failure) or {url, fail: true}."""
    out = []
    secconf = contract.get("security") or {}
    for entry in secconf.get("external_links_must_resolve", []) or []:
        if isinstance(entry, str):
            url, hard = entry, False
        else:
            url, hard = entry.get("url", ""), bool(entry.get("fail"))
        if not url:
            continue
        status, _, _, headers = fetcher.get(url, bust=False, timeout=25)
        ok = 200 <= status < 400
        if not ok:
            sev = FAIL if hard else WARN
            detail = headers.get("__error__", f"status {status}")
            out.append(Finding(sev, "GLOBAL", "external_link",
                               f"external link unreachable: {url} ({detail})"
                               + (" — this is the upload path; conversion-critical" if hard else "")))
    return out


def run_security_suite(fetcher, contract: dict, snaps: dict) -> list:
    secconf = contract.get("security") or {}
    findings = []
    for snap in snaps.values():
        findings += check_page_security(snap, secconf)
    findings += check_external_links(fetcher, contract)
    findings += check_ssl_expiry(contract, offline=fetcher.fixture_map is not None)
    return findings
