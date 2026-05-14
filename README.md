# Cyber Job Hunter

Automated cybersecurity job aggregator with profile-based scoring and live dashboard. Built as a portfolio project alongside the BeCode Brussels Blue & Red Team training, ahead of a September 2026 internship search.

[![CI](https://github.com/Jhatchi/cyber-job-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/Jhatchi/cyber-job-hunter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)](pyproject.toml)
[![Type-checked: mypy strict](https://img.shields.io/badge/type--checked-mypy%20strict-blue.svg)](pyproject.toml)

## What it does

Scrapes 18 cybersecurity job sources (Belgium, Luxembourg, EU, remote), filters them through a tunable profile, scores each posting on a 0-100 scale with full breakdown, and exposes the results in a Streamlit dashboard plus CSV export. Scraping respects `robots.txt`, rate limits each domain, backs off on errors, and trips a circuit breaker after repeated failures.

## Quick start

```bash
git clone https://github.com/Jhatchi/cyber-job-hunter.git
cd cyber-job-hunter
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python scripts/init_db.py && python scripts/run_scrape.py
streamlit run dashboard/app.py   # http://localhost:8501
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
       +------+-------+--------+
       v              v        v
   CSV export   Streamlit   Email digest
                dashboard   (planned)
```

## Features

### Working

**18 active scrapers across 6 categories:**

- *Big4 and ESN:* KPMG, Capgemini, Sopra Steria, Accenture, Devoteam, EPAM
- *Pure-play cyber:* NVISO, Toreon, Orange Cyberdefense, EASI, Nexova, Cream
- *Belgian public sector:* Smals, Actiris, Travaillerpour
- *EU institutions:* ENISA
- *Aggregators:* Remotive
- *Other Belgian tech:* itsme

**Engineering:**

- Centralized anti-abuse logic in `BaseScraper`: `robots.txt` parsing, configurable rate limit with random jitter, exponential backoff (5s, 15s, 45s), per-domain circuit breaker (3 failures, 1h cooldown), Cloudflare and captcha detection.
- Explainable scoring engine: 60+ target titles, 7 cyber keyword categories, location and language signals, rejection rules with line-by-line breakdown.
- Cyber relevance gate: postings with no target title and no tech keyword are rejected, preventing generalist ads from leaking into the top results.
- SHA-256 content deduplication and soft delete in `storage.py`.
- Streamlit dashboard with 3 tabs (Listing, Detail, Stats), 10+ filters, "new since last run" detection.
- CSV export filterable by score.
- Static User-Agent identified by a dedicated Proton Pass alias for revocability.

### Partial

- 🚧 HTTP caching via `hishel` (ETag, Last-Modified): wired in `BaseScraper`, not yet tuned per source.

### Planned

- ❌ Email digest (Gmail SMTP plus cron via launchd), Sprint 3.
- ❌ Cover letter generation via Anthropic API, Sprint 4.
- ❌ User-Agent rotation and proxy support.
- ❌ LinkedIn ingestion with ToS-aware safeguards, Sprint 4.
- ❌ ML-based scoring trained on thumbs up/down feedback.

## Screenshots

| Listing | Detail | Stats |
|---|---|---|
| ![Listing](docs/screenshots/01-listing.png) | ![Detail](docs/screenshots/02-detail.png) | ![Stats](docs/screenshots/03-stats.png) |

Listing: top 5 cards + filterable table. Detail: per-job scoring breakdown, matched keywords, rejection reasons. Stats: distributions by source, country, and keyword.

## Tech stack

| Layer | Library | Version |
|---|---|---|
| Language | Python | 3.11+ |
| HTTP client | httpx | >=0.27, <1.0 |
| HTTP caching | hishel | >=0.0.30 |
| HTML parsing | BeautifulSoup4 | >=4.12 |
| XML parsing | lxml | >=5.0 |
| RSS parsing | feedparser | >=6.0 |
| Validation | pydantic | >=2.6, <3.0 |
| ORM | sqlmodel | >=0.0.16 |
| Logging | loguru | >=0.7 |
| CLI | click | >=8.1 |
| Dashboard | streamlit + pandas | >=1.33, >=2.2 |
| Tests | pytest, pytest-cov, respx | >=8.1, >=5.0, >=0.21 |
| Lint and security | ruff (with bandit `S` selector) | >=0.4 |
| Type checking | mypy (strict mode) | >=1.10 |

## Project metrics

| Metric | Value |
|---|---|
| Python LOC (src + tests + dashboard + scripts) | 12 257 |
| Tests | 357 passing |
| Coverage | 89% on `src/` (excluding Streamlit UI dashboard) |
| Active scrapers | 18 |
| Type safety | mypy `strict = true` |
| Lint and security | ruff with `S` (bandit) selector |

Run locally:

```bash
pytest --cov=src --cov-report=term
ruff check . && mypy src
```

## Active sources

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

Deferred sources (with documented reasons in `config/sources.yaml`): CCB and EGov Select (anti-bot Akamai), cybersecurity.lu (React SPA, no public JSON), Spotit, Moovijob.lu (Cloudflare), CERT-EU (EU SECRET clearance required), LinkedIn (Sprint 4, ToS-aware safeguards).

## Scoring rules

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

The breakdown is exposed line by line in the dashboard Detail tab, including matched keywords and rejection reasons.

## Profile

Targeted roles: SOC Analyst Junior, Cybersecurity Intern, Blue Team Trainee, Detection Engineer Junior, GRC Junior, Threat Intel Junior, IR Junior, Young Graduate Cyber, IAM, Cloud Security, Pentester. Location priority: Brussels > Wallonia, Luxembourg. Languages: FR + EN, or EN-only, or FR-only. Full profile in [`config/profile.yaml`](config/profile.yaml).

## Anti-abuse practices

- Honest `User-Agent` with a dedicated contact alias (Proton Pass).
- `robots.txt` respected via `urllib.robotparser`.
- Rate limit 2 to 5 seconds plus random jitter per domain.
- Exponential backoff on transient errors: 5s, 15s, 45s (3 retries max).
- Per-domain circuit breaker: 3 consecutive 4xx or 5xx failures disable the source for 1 hour.
- Cloudflare and captcha detection via word-boundary regex, then clean abort.
- No retry on terminal 4xx (404, 403 when not bot-related).
- Pagination cap configurable per source (default 5).
- LinkedIn and Indeed disabled by default.

## Data and privacy

Job postings are public data. The aggregator does not collect personal data on applicants or recruiters. SQLite database stays local. No third-party analytics. User-Agent identifies the project with a dedicated contact email for revocability.

## Roadmap

- ✅ Sprint 1 (April 2026): bootstrap, models, scoring, filters, SQLite storage, 4 scrapers.
- ✅ Sprint 2 (April 2026): Streamlit dashboard, "new postings" detection, +14 scrapers (Smals, Cream, Travaillerpour, Actiris, Accenture, KPMG, Capgemini, Orange Cyberdefense, Devoteam, Sopra Steria, Nexova, EPAM, Toreon, ENISA), cyber relevance gate.
- 🚧 Sprint 3: Gmail SMTP digest with launchd cron, Forem, StepStone, Jobat (TOS permitting), Workday Proximus.
- 🚧 Sprint 4: Anthropic-powered cover letter drafts, LinkedIn ingestion with safeguards, ML scoring from thumbs up/down feedback.

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
    scoring.py           0-100 with breakdown
    deduplication.py     SHA-256 content hash
    storage.py           JobRepository (SQLite)
    scrapers/            base.py + 18 concrete scrapers
  dashboard/             Streamlit app, 3 views
  scripts/               init_db.py, run_scrape.py, export_csv.py
  tests/                 357 tests, respx mocks
```

## Contributing

Personal portfolio project, but issues, PRs, and suggestions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for code conventions.

## License

[MIT](LICENSE), 2026 Jhatchi.
