# Enormous Door AI/Search Optimization Handoff
## Autopilot Deployment Edition — All Pages Complete / Background System Built

**Project:** Enormous Door Mastering AI/Search Optimization
**Handoff date:** 2026-07-07
**Supersedes:** the 2026-07-06 handoff ("Mixing Complete / Pricing Update / Next: Vinyl")
**Purpose:** Continue this project in any fresh chat without losing page status,
the July 7 audit results, Squarespace-specific lessons, or the Autopilot system state.

> **Important:** once the Autopilot repo is running, its auto-generated
> `STATUS.md` is the authoritative record of live page state — it updates
> nightly. This handoff covers everything STATUS.md can't: decisions,
> lessons, guardrails, and system architecture.

---

# 1. Project Context (unchanged)

**Business:** Enormous Door Mastering — heavy music mastering (metal, punk,
hardcore, doom, death, black metal, grind) for vinyl, streaming, CD, cassette, digital.
**Lead:** Jack Control / Jack Conrow.
**Premium tier:** Beyond Heavy — Jack Control + Maor Appelbaum.
**Mixing:** curated engineer network, same intake funnel.
**Main conversion URL:** `/launch-contact`
**Mix-prep URL:** `/technical-faq#mix-prep`
**Canonical host:** `https://enormousdoor.com` (non-www)

---

# 2. Page Status — verified live 2026-07-07

All pages COMPLETE. Do not reopen unless a specific issue appears or the
sentinel flags one.

| Page | H1 | SEO Title | Notes |
|---|---|---|---|
| `/` | HEAVY MUSIC MASTERING | Heavy Music Mastering \| Enormous Door Mastering | Hero, CTAs, Mix Prep link all in spec |
| `/pricing` | HEAVY MUSIC MASTERING PRICING | Heavy Music Mastering Pricing \| Enormous Door Mastering | **New title/H1 July 7.** H1 lives in the code block (no Squarespace H1 — one H1 total, valid). LP/45 = $500/$600 live in table + estimator + site-wide header JSON-LD |
| `/beyond-heavy` | BEYOND HEAVY MASTERING | Beyond Heavy Mastering \| Jack Control + Maor Appelbaum | Unchanged |
| `/launch-contact` | START YOUR PROJECT | Start Your Project \| Mixing & Heavy Music Mastering | Form verified working |
| `/technical-faq` | MIX PREP & DELIVERY SPECS | Mix Prep for Mastering \| Heavy Music Mastering Specs | **Rebuilt July 7:** crawler access RESTORED after a temporary robots block; H1 moved to top; Q&A-formatted H3s (excellent for AI retrieval) |
| `/mixing` | HEAVY MUSIC MIXING | Heavy Music Mixing \| Enormous Door Mixing Team | Unchanged |
| `/vinyl-mastering` | VINYL MASTERING | (in spec) | Links to /vinyl-times guide |
| `/vinyl-pressing` | VINYL PRESSING | (in spec) | **Helios CTAs are INTENTIONAL** — Helios pressing projects needing mastering route to Enormous Door by default. Do not "fix" |
| `/vinyl-times` | (single H1) | (title has minor typo: "Levels, Levels") | Crawlable side-length table = prime AI-citable asset |
| `/how-to-proceed` | (single H1) | (in spec) | **Steps consolidated into ONE text block July 7** — DOM order now correct |
| `/clients` | (single H1) | (in spec) | Real press quotes (Pitchfork, Last Rites, Metal Injection) — strong E-E-A-T |
| `/gear`, `/about` | monitored | — | Baseline-tracked only |

**Retired:** `/test` and `/faqs` deleted/301'd July 4–5. Stale search
listings are index lag only; sentinel alarms if either serves 200 again.

**Not Linked pages (public unless hidden!):** PARTNER = engineer
application (indexing optional, owner's choice). MAOR MIXING PREP TIPS =
linked PDF for homepage app; PDFs are indexable and can't be noindexed on
Squarespace — aware, not acting; fix only if it ever outranks
/technical-faq. Utility pages (Assets, Testimonial Carousel, video reels,
Fast Lane) should be "hide from search" — verify done.

**Sitewide:** footer socials now point to the business Facebook page and
Discogs label profile (good entity signals). All `#mix-prep` anchors
entered via URL field with new-tab off.

**Pending verification (may already be done):** one-time Search Console
indexing requests for `/pricing`, `/technical-faq`, `/how-to-proceed`
after their July 7 meaningful changes.

---

# 3. Guardrails (original set + July 7 additions)

Original (all still binding): no footer schema cleanup scripts, no
MutationObserver patches, no dynamic Squarespace schema rewriting, no
LocalBusiness repair scripts, no Review/AggregateRating schema for
testimonials, no VideoObject schema to chase video indexing, no re-request
of indexing without a meaningful change, mix-prep questions route to
`/technical-faq#mix-prep` never Recording Roadmap, pricing changes update
ALL THREE locations (visible table, estimator JS, **site-wide Header Code
Injection** JSON-LD — not page-level injection).

**New, learned July 7:**
1. **Never trust a single fetch.** CDN/edge caches serve stale copies;
   a fetched "problem" must be confirmed with a fresh cache-busted
   re-fetch before anyone acts. (The Autopilot enforces this automatically.)
2. **Squarespace link editor drops URL fragments** when a page is picked
   from the internal dropdown — anchors must be pasted into the URL field.
3. **Squarespace SEO Title field overrides Page Title** — edits to the
   wrong field silently don't ship.
4. **"Not Linked" pages are live and indexable** unless individually hidden.
5. **Visual order ≠ DOM order** in Squarespace grids — crawlers read DOM;
   keep sequences in a single text block.
6. **Squarespace robots/crawler settings can block individual paths** —
   the /technical-faq incident. The sentinel checks nightly.

---

# 4. The Autopilot System (built + tested 2026-07-07)

Repo package: `enormous-door-autopilot.zip`. Six offline test scenarios
pass. Architecture:

- **Nightly Site Sentinel** (free, deterministic): all page contracts,
  routing incl. anchors, pricing in 3 locations with $520/$620 tripwires,
  schema guardrails, robots + AI-crawler access (GPTBot, ClaudeBot,
  PerplexityBot, Google-Extended…), retired pages, content diffs.
  Cache-busted fetches + double confirmation → no false alarms.
- **Security suite** (rides nightly, free): SSL expiry, mixed content,
  HSTS, response-time budget, WeTransfer (hard-fail) / Helios link
  liveness, defacement alarm (≥60% single-run rewrite), /launch-contact
  form-field integrity.
- **Weekly AI Visibility Panel** (API, ~cents–$ per run): 24 buyer
  questions × 5 categories via Claude + web search; share-of-voice
  trendline; drop alerts; gaps exported.
- **Weekly Content Engine** (API): drafts 1 AI-retrieval-optimized page
  targeting the top visibility gap + 4 social posts; opens a
  `content-ready` issue. Publishing = human paste (~10 min/week;
  Squarespace has no page-creation API).
- **Monthly Lighthouse** (free): perf/SEO/a11y scores with thresholds.
- **Optional Search Console pull** (free): real query/click trendline
  via service-account secrets.
- **MCP server** (no scheduled spend): 12 tools for Claude Desktop/Code —
  run_full_check, check_page, verify_pricing, check_crawler_access,
  check_security, diff_page, get_status, get_latest_report,
  get_visibility_trend, get_pending_social_drafts, get_content_drafts,
  list_monitored_pages. Social drafts schedule via the OneUp connector
  in one message.

Alert channels (GitHub Issues, auto-close on recovery): `sentinel-alert`,
`visibility-alert`, `content-ready`, `perf-alert`.

**Deployment status at handoff:** code complete and self-tested; NOT yet
deployed. Remaining human steps: create private GitHub repo → push folder
(incl. `.github/`) → add `GROQ_API_KEY` secret → run each workflow
once to baseline → configure MCP per README.

**Weekly human loop (~10 min):** paste the drafted page into Squarespace,
publish, request indexing once, tell Claude to schedule social via OneUp
and add the new page to `site_contract.yaml`.

---

# 5. Fresh Chat First Prompt

```text
Continue the Enormous Door AI/Search Optimization project using the
uploaded HANDOFF.md (Autopilot Deployment Edition, 2026-07-07).

All site pages are COMPLETE and verified live as of 2026-07-07 — do not
reopen any page unless the sentinel flags it or I report a specific issue.
Key facts: Pricing H1 is HEAVY MUSIC MASTERING PRICING (in the code block;
single H1, valid), LP/45 pricing is $500/$600 in all three locations,
/technical-faq crawler access is restored with H1 at top, Vinyl Pressing's
Helios CTAs are intentional, /test and /faqs are retired.

All original guardrails hold, plus the July 7 additions: never trust a
single fetch (confirm with cache-busted re-fetch), Squarespace link editor
drops anchors (paste full URL), SEO Title field overrides Page Title,
Not Linked pages are public, DOM order ≠ visual order in grids.

The Autopilot system (enormous-door-autopilot.zip) is built and
self-tested: nightly deterministic sentinel + security suite, weekly
24-question AI-visibility panel, weekly content engine, monthly
Lighthouse, optional Search Console pull, and a 12-tool MCP server.

Current task: [pick one]
(a) help me deploy the Autopilot repo and interpret its first runs;
(b) the sentinel flagged an issue — investigate and give me the exact
    Squarespace fix;
(c) this week's content draft is ready — review it against the site
    voice and guardrails before I paste it;
(d) review the visibility trendline and adjust the question panel or
    content backlog.
```

---

# 6. Final Notes

Once the repo runs nightly, prefer `STATUS.md` + `reports/` over this
document for current page state — this file is the narrative memory;
those are the live facts. Update this handoff only when decisions or
guardrails change, not for routine state (the system handles that).
