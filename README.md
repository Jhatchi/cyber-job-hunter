# Cyber Job Hunter

Automated cybersecurity job aggregator with profile-based scoring and a live Streamlit dashboard. Built solo during the BeCode Brussels Blue & Red Team bootcamp, targeting a September 2026 internship.

[![CI](https://github.com/Jhatchi/cyber-job-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/Jhatchi/cyber-job-hunter/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-357%20passing-brightgreen.svg)](#project-metrics)
[![Coverage](https://img.shields.io/badge/coverage-89%25-brightgreen.svg)](#project-metrics)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Type-checked](https://img.shields.io/badge/mypy-strict-blue.svg)](pyproject.toml)
[![Lint](https://img.shields.io/badge/ruff-bandit_S-black.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Johan--Emmanuel%20Hatchi-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/johan-emmanuel-hatchi/)

## Screenshots

![Listing view](docs/screenshots/01-listing.png)

<details>
<summary>Detail and Stats views</summary>

![Detail view](docs/screenshots/02-detail.png)
![Stats view](docs/screenshots/03-stats.png)

</details>

## What it does

- **Scrapes 18 cybersecurity job sources** across Belgium, Luxembourg and the EU (Big4, pure-play cyber, public sector, ENISA, remote aggregators).
- **Scores each posting 0 to 100** through a tunable profile (target titles, seniority, languages, location) with a line-by-line breakdown of why the score is what it is.
- **Surfaces results in a Streamlit dashboard** plus CSV export, with "new since last run" detection and 10+ filters.

## Tech stack

**Core:** Python 3.11+, httpx, BeautifulSoup4, lxml, feedparser, pydantic v2, SQLModel (SQLite), loguru, click
**HTTP caching:** hishel (ETag, Last-Modified)
**Dashboard:** Streamlit, pandas
**Quality:** pytest + respx, ruff (with bandit `S` selector), mypy strict, GitHub Actions CI

## Quick start

```bash
git clone https://github.com/Jhatchi/cyber-job-hunter.git && cd cyber-job-hunter
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python scripts/init_db.py && python scripts/run_scrape.py && streamlit run dashboard/app.py
```

Dashboard at `http://localhost:8501`.

## Project metrics

| Metric | Value |
|---|---|
| Python LOC (`src` + `tests` + `dashboard` + `scripts`) | 12 257 |
| Tests | 357 passing |
| Coverage on `src/` | 89% (Streamlit UI excluded) |
| Active scrapers | 18 across 6 categories |
| Type safety | mypy `strict = true` |
| Security lint | ruff with `S` (bandit) selector |
| CI | GitHub Actions: ruff + mypy + pytest on every push |

Run locally:

```bash
pytest --cov=src --cov-report=term
ruff check . && mypy src
```

## Architecture

```
config/ (profile.yaml + sources.yaml)
              |
              v
     BaseScraper (ABC)
     rate limit, jitter, exponential backoff,
     circuit breaker, robots.txt, bot detection
              |
   +----------+-----------+
   v                      v
 REST / RSS / Workday   HTML scrapers
   |                      |
   +----------+-----------+
              v
       JobBase (Pydantic v2)
              |
              v
       filters.py  (rejection rules, cyber relevance gate)
              |
              v
       scoring.py  (0-100 with explainable breakdown)
              |
              v
       storage.py  (SQLite via SQLModel, SHA-256 dedup)
              |
       +------+-------+
       v              v
   CSV export   Streamlit dashboard
```

Centralized anti-abuse logic in `BaseScraper`: every scraper (REST, RSS, Workday, HTML) inherits rate limiting, backoff, circuit breaker and `robots.txt` parsing without duplication. New sources only implement their domain-specific parsing.

## Scoring engine

Each posting scores 0 to 100 against a tunable profile (`config/profile.yaml`). Scores are **explainable**: the dashboard Detail tab shows every rule that fired, with matched keywords and rejection reasons.

**Headline signals:**

- `+30` target title match (SOC Analyst, IAM, Pentester, GRC Junior, ...)
- `+15` junior / intern / trainee / 0-2 years
- `+10` Brussels location, or "graduate program"
- `+5` per tech keyword across 7 cyber categories (cap `+30`)

**Penalties and rejections:**

- `-20` "Master mandatory" with no alternative
- Auto-reject: `5+ years`, Senior / Lead / Manager, NL B2+ required without EN or FR fallback, no target title AND no tech keyword (cyber relevance gate)

<details>
<summary>Full rule set</summary>

```
+30  target title match (SOC Analyst, IAM, Pentester, GRC Junior, etc.)
+15  "junior, intern, trainee, 0-2 years"
+10  "young graduate" in title OR "graduate program" in description
+5   per matched tech keyword (cap +30), 7 cyber categories
+10  Brussels                     +5   Wallonia, Luxembourg, BE-LU fallback
+10  FR + EN     +8 EN-only       +8 FR-only      +5 NL "nice to have"
-5   "Bachelor required" with no alternative
-20  "Master mandatory" with no alternative
-10  "3+ years"

Rejected (score = 0):
- "5+ years", Senior, Lead, Manager, Principal, Team Lead
- NL B2/C1/C2 required with no EN or FR alternative
- Flanders location with no "English only" mention
- Cyber relevance gate: no target title AND no tech keyword
```

</details>

## Sources

18 active scrapers across 6 categories:

| Category | Sources |
|---|---|
| **Big4 and ESN** | KPMG, Capgemini, Sopra Steria, Accenture, Devoteam, EPAM |
| **Pure-play cyber** | NVISO, Toreon, Orange Cyberdefense, EASI, Nexova, Cream |
| **Belgian public sector** | Smals, Actiris, Travaillerpour |
| **EU institutions** | ENISA |
| **Aggregators** | Remotive |
| **Other Belgian tech** | itsme |

Scraping techniques span REST JSON, RSS, Workday CXS, Next.js `_next/data`, XML sitemaps and plain HTML. Each source has its own config block in [`config/sources.yaml`](config/sources.yaml).

<details>
<summary>Full source table with technique and country</summary>

| Source | Type | Country | Notes |
|---|---|---|---|
| [Remotive](https://remotive.com) | REST JSON | Remote | Strict TOS: 4 req/day, 24h delay, attribution. |
| [NVISO](https://nviso.eu/jobs/) | HTML | BE, DE, GR, AT | Pure-play cyber, left Recruitee in April 2026. |
| [itsme](https://itsme-id.com) | Recruitee API | BE | Brussels digital identity platform. |
| [EASI](https://easi.net/en/jobs) | HTML | BE | ESN, Wallonia and Flanders. |
| [Smals](https://www.smals.be/en/jobs/list) | HTML (Drupal) | BE | ICT for Belgian social security. |
| [Cream by Audensiel](https://www.creamconsulting.com/jobs) | HTML | LU | Cyber ESN, Luxembourg. |
| [Travaillerpour.be](https://travaillerpour.be) | HTML (Drupal) | BE | Federal job portal (FOD, SPF, NCCN). |
| [Actiris](https://www.actiris.brussels) | XML sitemap + HTML | BE | Brussels employment service, 40 most recent per run. |
| [Accenture](https://www.accenture.com/be-en/careers) | Workday CXS API | BE | Belgium facet applied. |
| [KPMG Belgium](https://kpmg-career.talent-soft.com) | RSS (TalentSoft) | BE | Full feed, cyber filtered downstream. |
| [Capgemini](https://www.capgemini.com/be-en/jobs) | REST (Azure) | BE | `search=cyber` preapplied. |
| [Orange Cyberdefense](https://jobs.orangecyberdefense.com) | HTML (TeamTailor) | BE, EU | Listing plus per-job detail enrichment. |
| [Devoteam](https://www.devoteam.com/jobs) | REST (GCP Cloud Talent) | BE | Native country filter. |
| [Sopra Steria](https://careers.soprasteria.be) | HTML (Attrax) | BE | JSON-LD `JobPosting` on detail pages. |
| [Nexova Group](https://www.nexovagroup.eu) | HTML | BE | Cyber and defense, ESA-Redu SOC. |
| [EPAM](https://careers.epam.com/en/jobs/belgium) | Next.js `_next/data` | BE | Build ID extracted dynamically from `__NEXT_DATA__`. |
| [Toreon](https://www.toreon.com/jobs/) | HTML | BE | Pure-play cyber consulting, Antwerp HQ. |
| [ENISA](https://www.enisa.europa.eu/careers) | HTML | EU | EU cybersecurity agency, Athens HQ. |

</details>

**Deferred sources** (documented in `config/sources.yaml`): CCB and EGov Select (Akamai anti-bot), cybersecurity.lu (React SPA, no public JSON), Spotit, Moovijob.lu (Cloudflare), CERT-EU (EU SECRET clearance required), LinkedIn (planned with ToS-aware safeguards).

## Anti-abuse and ethics

Job postings are public data, but scraping them responsibly is non-trivial. Centralized in `BaseScraper`:

- **`robots.txt` respected** via `urllib.robotparser` before every fetch.
- **Honest `User-Agent`** identifying the project, with a dedicated Proton Pass contact alias (revocable).
- **Rate limit** 2 to 5 seconds plus random jitter per domain.
- **Exponential backoff** on transient errors: 5s, 15s, 45s (3 retries max), then circuit breaker.
- **Per-domain circuit breaker**: 3 consecutive 4xx or 5xx failures disable the source for 1 hour.
- **Cloudflare and captcha detection** via word-boundary regex, with clean abort (no retry storms).
- **No retry on terminal 4xx** (404, 403 when not bot-related).
- **Pagination cap** configurable per source (default 5).
- **LinkedIn and Indeed disabled by default**.

The aggregator collects no personal data on applicants or recruiters. SQLite database stays local. No third-party analytics, no telemetry.

## Known limits

- **No JavaScript rendering.** Cloudflare-protected or fully client-rendered sources (Moovijob.lu, cybersecurity.lu, Spotit, EGov Select) are deferred. Adding Playwright would unblock them but at the cost of CI complexity and runtime: deliberate trade-off, not an oversight.
- **Streamlit UI excluded from coverage.** The 89% applies to `src/`. Dashboard widgets are exercised manually. Adding `streamlit-testing` is on the backlog but low priority versus shipping new scrapers.
- **Scoring is rule-based, not learned.** Weights are tuned by hand against the user's profile. A thumbs up/down feedback loop and ML scoring are planned (Sprint 4).
- **Single profile, local SQLite.** No multi-user, no remote DB. Designed as a personal tool, not a SaaS. Migration to Postgres + multi-profile would be additive but is out of scope.
- **Geographic scope: Belgium, Luxembourg, EU institutions, remote.** France/Netherlands/Germany not covered. Easy to add (new YAML entries), just not the current focus.
- **No alerting yet.** New postings are surfaced in the dashboard but no email or push. Gmail SMTP digest with launchd cron is the next milestone (Sprint 3).

## Roadmap

- ✅ **Sprint 1** (April 2026): bootstrap, Pydantic models, scoring engine, filters, SQLite storage, 4 scrapers.
- ✅ **Sprint 2** (April 2026): Streamlit dashboard, "new since last run" detection, 14 additional scrapers (Smals, Cream, Travaillerpour, Actiris, Accenture, KPMG, Capgemini, Orange Cyberdefense, Devoteam, Sopra Steria, Nexova, EPAM, Toreon, ENISA), cyber relevance gate.
- 🚧 **Sprint 3**: Gmail SMTP digest via launchd cron, Forem, StepStone, Jobat (TOS permitting), Workday Proximus.
- 🚧 **Sprint 4**: Anthropic-powered cover letter drafts, LinkedIn ingestion with safeguards, ML scoring trained on thumbs up/down feedback.

## Project layout

```
cyber-job-hunter/
  pyproject.toml         ruff, mypy strict, pytest config
  requirements.txt
  .env.example
  config/                profile.yaml, sources.yaml
  src/
    models.py            Job, ScoreResult, ScrapeRun
    config.py            Pydantic loaders
    filters.py           rejection rules, cyber relevance gate
    scoring.py           0-100 with explainable breakdown
    deduplication.py     SHA-256 content hash
    storage.py           JobRepository (SQLite)
    scrapers/            base.py + 18 concrete scrapers
  dashboard/             Streamlit app, 3 views
  scripts/               init_db.py, run_scrape.py, export_csv.py
  tests/                 357 tests, respx mocks
```

## Contributing

Personal portfolio project, but issues and PRs are welcome. Code conventions in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE), 2026 Jhatchi.

## About

Built solo by **Johan-Emmanuel Hatchi** ([GitHub](https://github.com/Jhatchi) · [LinkedIn](https://www.linkedin.com/in/johan-emmanuel-hatchi/)) during the [BeCode Brussels](https://becode.org) Blue & Red Team bootcamp (November 2025 to September 2026). Open to cybersecurity internship opportunities starting September 2026 in Belgium.
