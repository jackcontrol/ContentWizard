# EnormousDoorContentWizard

Enormous Door Content Wizard — AI-guided social media content tool for
enormousdoor.com, plus the **Sentinel** automation suite that monitors the
site and drafts content on a schedule.

## Layout

- `EnormousDoorContentWizard.py` — desktop GUI content tool (Windows build
  scripts: `build_EnormousDoor_v*.bat`, deps: `requirements_windows_build.txt`)
- `Sentinel/` — all automation scripts, config (`site_contract.yaml`), state,
  and reports. See [Sentinel/README.md](Sentinel/README.md) for setup,
  required GitHub Actions secrets (`GROQ_API_KEY`, optional GSC secrets),
  and how each check works.

## Scheduled workflows (`.github/workflows/`)

All jobs run with `working-directory: Sentinel` and install
`Sentinel/requirements.txt`.

| Workflow | Schedule | What it does |
|---|---|---|
| `sentinel.yml` | nightly | Site health checks; opens/closes alert issues |
| `visibility.yml` | weekly Mon | 24-question AI visibility panel (Groq compound, web search) |
| `content.yml` | weekly Mon | Drafts pages/social posts from visibility gaps (Groq) |
| `lighthouse.yml` | monthly | Lighthouse audit of key pages; threshold alerts |

Each workflow also has a manual "Run workflow" button (`workflow_dispatch`).
