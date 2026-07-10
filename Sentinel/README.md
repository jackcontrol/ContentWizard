# Enormous Door Autopilot

Hands-off background system for **enormousdoor.com**: site integrity,
security, AI-search visibility, content production, and conversion
protection. Deterministic where it must be ruthless; AI-powered only
where growth needs judgment; conversational through MCP when you want
to talk to it.

## Architecture at a glance

| Layer | Schedule | Engine | Cost |
|---|---|---|---|
| **Site Sentinel** — routing, pricing×3, schema guardrails, H1/titles, robots + AI-crawler access, retired pages, diffs | Nightly 3:17 AM | Deterministic | Free |
| **Security suite** — SSL expiry, mixed content, HSTS, response-time budget, WeTransfer/Helios links, defacement alarm, intake-form integrity | Rides with sentinel | Deterministic | Free |
| **AI Visibility Panel** — 24 buyer questions × 5 categories, share-of-voice trendline, drop alerts, gap export | Weekly Mon AM | Claude + web search | ~cents–few $/run* |
| **Content Engine** — 1 paste-ready page draft + 4 social drafts/week, targeted at visibility gaps | Weekly Mon AM | Claude | ~cents/run* |
| **Lighthouse Audit** — perf/SEO/accessibility scores, regression thresholds | Monthly | Deterministic | Free |
| **Search Console pull** (optional) — real queries/clicks/positions trendline | Weekly | Deterministic | Free |
| **MCP server** — 12 on-demand tools for Claude Desktop/Code | On demand | Your Claude session | No scheduled spend |

\* Verify current model pricing at https://docs.claude.com/en/api/overview.
A realistic total for both weekly AI jobs is a few dollars per month.

## Setup (~15 minutes)

1. **Create a private GitHub repo**, push this folder to its root
   (including the hidden `.github/` directory).
2. **Add secret** `ANTHROPIC_API_KEY` (repo Settings → Secrets → Actions)
   — key from https://console.anthropic.com. This powers the visibility
   panel and content engine. Everything else runs without it.
3. Enable Actions notifications for failures (GitHub Settings →
   Notifications). Alerts also arrive as labeled GitHub Issues:
   `sentinel-alert` (red — site broken, confirmed twice),
   `visibility-alert` (AI share of voice dropped),
   `content-ready` (weekly drafts waiting),
   `perf-alert` (Lighthouse regression).
4. **First run:** Actions → Site Sentinel → Run workflow. This baselines
   content hashes. Then run the Visibility Panel once to seed the
   trendline and gap list, then the Content Engine for your first draft.

### MCP server (Claude Desktop / Claude Code)

```bash
git clone <your repo> && cd <repo>
pip install -r requirements-local.txt
```

Claude Desktop — `claude_desktop_config.json`:
```json
{ "mcpServers": { "ed-sentinel": {
    "command": "python",
    "args": ["/ABSOLUTE/PATH/mcp_server.py"],
    "cwd": "/ABSOLUTE/PATH" } } }
```
Claude Code: `claude mcp add ed-sentinel -- python /ABSOLUTE/PATH/mcp_server.py`

Then just talk: *"run a full site check"* · *"I just edited pricing —
verify it"* · *"are AI crawlers still allowed?"* · *"what changed on the
homepage?"* · *"show this week's social drafts"* → *"schedule them
through OneUp"* (with your OneUp connector in the same client, Claude
reads drafts from one tool and schedules with the other).

`git pull` in the repo folder now and then so MCP sees fresh state, or
ask Claude to do it.

## The weekly rhythm (your total hands-on time: ~10 min)

Monday morning, automatically: the visibility panel measures which of
24 buyer questions mention Enormous Door; unanswered questions become
targets; an hour later the content engine drafts the page most likely
to win the top gap, plus social posts; a `content-ready` issue lands
with everything paste-ready.

Your 10 minutes: paste the page into Squarespace, publish, request
indexing once, tell Claude to schedule the social drafts via OneUp and
add the new page to `site_contract.yaml` — from that night, the sentinel
guards the new page too. Over months this compounds: every gap that gets
a page becomes a question where AI engines have your content to cite.

## What is deliberately NOT automated (honesty section)

- **Publishing to Squarespace** — no page-creation API exists; drafts
  are paste-ready, pasting is human.
- **Search Console indexing requests** — per the project guardrails,
  requested once per meaningful change, by you.
- **Any edit to the live site** — the system detects and drafts;
  it never touches.
- **Backlink/PR outreach emails** — automated outreach burns sender
  reputation; ask Claude (with this MCP) to draft targeted pitches when
  a strong new page ships.

## Updating pricing (the 3-location rule, automated QA)

Edit the site (table, estimator, header JSON-LD), then in
`site_contract.yaml` swap new values into `required_patterns` /
`jsonld.prices_required` / `estimator_patterns` and move old values into
the forbidden lists. Run the sentinel workflow — it executes the full
pricing QA checklist and confirms the stale values are gone everywhere.
Or just tell Claude: *"verify pricing"* (MCP `verify_pricing` checks all
three locations live).

## Files

```
site_contract.yaml      single source of truth — pages, prices, guardrails,
                        security config, visibility panel, content backlog
sentinel.py             core engine: crawl, check, confirm, diff, report
checks_ext.py           security & conversion-integrity suite
visibility_probe.py     weekly AI share-of-voice panel (API)
content_engine.py       weekly draft generator (API)
mcp_server.py           12 on-demand tools for Claude Desktop/Code
perf_summary.py         Lighthouse score parsing + thresholds
search_console_pull.py  optional GSC trendline (service-account secrets)
.github/workflows/      sentinel (nightly) · visibility (weekly) ·
                        content (weekly) · lighthouse (monthly)
STATUS.md               auto-generated living site status
reports/ state/         reports, trendlines, baselines, draft logs
tests/run_self_test.py  offline suite: 6 scenarios, no network needed
```

## Run locally

```bash
pip install -r requirements.txt
python sentinel.py --fail-on-alert     # full live check
python tests/run_self_test.py          # offline self-test
```
