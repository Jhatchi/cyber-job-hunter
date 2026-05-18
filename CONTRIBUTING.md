# Contributing

Personal project but issues, PRs and suggestions are welcome. A few conventions to keep the codebase consistent.

## Local setup

```bash
git clone https://github.com/Jhatchi/Cyber-Job-Hunter.git
cd Cyber-Job-Hunter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest  # verifies everything passes (357 tests)
```

## Conventions

### Commits: Conventional Commits

Format: `<type>(<scope>): <short imperative description>`

Types in use:

- `feat(...)`: new feature
- `fix(...)`: bug fix
- `chore(...)`: maintenance, deps, config (no user-facing change)
- `refactor(...)`: restructuring with no behavior change
- `test(...)`: tests only
- `docs(...)`: documentation

Common scopes: `scrapers`, `scoring`, `filters`, `dashboard`, `storage`, `config`, `models`.

Example commits from this repo:

```
feat(scrapers): add NVISO HTML scraper after Recruitee migration
fix(filters): refine Dutch detection to handle accent-insensitive patterns
chore(scrapers): use Proton Pass alias for User-Agent contact email
```

### Code style

- **Type hints** on every public signature.
- **`ruff`** for linting (config in `pyproject.toml`).
- **`mypy`** strict (tolerated: `Any` when justified, with commented `type: ignore`).
- **Docstrings** in English on public modules and classes.
- **Comments** are sparse: a comment explains the *why*, not the *what*.

```bash
ruff check src/ dashboard/ tests/
ruff format src/ dashboard/ tests/
mypy src/
```

### Tests

- Every new module must be tested.
- Target: **80%+ coverage** on business modules (`src/`, `dashboard/data.py`).
- **`respx`** to mock `httpx` in scrapers. NEVER hit the network in unit tests.
- Integration tests (scrapers to DB to scoring): use DB fixtures in `tmp_path`.
- Streamlit UI tests not required (covered by smoke tests).

### Adding a new scraper

1. **Read-only HTTP recon** on the target site: check `robots.txt`, HTML/API structure.
2. Create `src/scrapers/<name>.py` inheriting from `BaseScraper`.
3. Implement only `fetch_jobs(self, page) -> tuple[list[JobBase], bool]`.
4. Add `JobSource.<NAME>` in `src/models.py`.
5. Register in `src/scrapers/__init__.py` (`SCRAPER_FACTORIES`).
6. Configure in `config/sources.yaml` (with `enabled: true` and documented `notes:`).
7. Add `tests/test_<name>.py` with representative HTML/JSON fixtures and at least 6 tests.
8. Run `python scripts/run_scrape.py --source <name>` to validate live.

## Security

- ⚠️ **Do not commit**: `.env`, `data/jobs.db`, logs, secrets, real HTTP payloads containing PII.
- If a secret is committed by mistake: **revoke** it immediately, then clean git history (BFG or `git filter-repo`).
- LinkedIn: only add the scraper with strict safeguards (rate 1/3s, max 200/day, abort on bot detection, opt-in via config flag).

## Code of conduct (light)

- No bot abuse: respect `robots.txt`, rate-limit, and back off gracefully when a site does not want us.
- The project collects public job postings only; no personal data on recruiters is stored.

## Questions and contact

GitHub issue, or via the `User-Agent` contact alias (Proton Pass).
