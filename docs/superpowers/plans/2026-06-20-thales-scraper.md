# Thales Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une source `thales` au job hunter qui scrape les offres belges depuis le site careers Phenom de Thales.

**Architecture:** `ThalesScraper(BaseScraper)` lit le HTML rendu côté serveur, extrait le bloc JSON embarqué `phApp.ddo.eagerLoadRefineSearch.data.jobs`, filtre `country == "Belgium"` côté client, pagine via `?from=N&s=1` jusqu'à épuisement (`has_next`), puis enrichit chaque offre BE avec la description complète depuis le JSON-LD `JobPosting` de sa page détail.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup/lxml (via helpers `base.py`), pydantic/SQLModel, pytest + respx.

## Global Constraints

- Langue des commentaires/docstrings : français (cohérent avec le code existant).
- Aucune mention de Claude/Anthropic/Co-Authored dans les commits.
- Scanner avec semgrep avant chaque commit.
- Respecter robots.txt : laissé à `BaseScraper._robots_allowed` (config `respect_robots_txt: true`). robots.txt de Thales n'interdit ni `/search-results` ni `/job/`.
- Le scraper ne filtre PAS le cyber : c'est le `scoring` qui le fait en aval.
- Réutiliser les helpers existants de `base.py` (`extract_jobposting_jsonld`, `clean_html_to_text`) — DRY, pas de nouvelle dépendance.
- Société figée à `"Thales"` (comme les autres scrapers hardcodent leur company).

---

### Task 1: Cœur du scraper — extraction, filtrage BE, pagination

**Files:**
- Modify: `src/models.py` (enum `JobSource`, ajouter `THALES = "thales"`)
- Create: `src/scrapers/thales.py`
- Test: `tests/test_thales.py`

**Interfaces:**
- Consumes: `BaseScraper`, `JobBase`, `Country`, `JobSource` (existants).
- Produces:
  - `ThalesScraper(BaseScraper)` avec `name="thales"`, `source=JobSource.THALES`
  - `ThalesScraper.fetch_jobs(page: int) -> tuple[list[JobBase], bool]`
  - module-level `_extract_ddo(html: str) -> dict[str, Any]`
  - module-level `_parse_posted_at(value: str | None) -> datetime | None`
  - module-level `_slugify(title: str) -> str`
  - méthode `ThalesScraper._parse_job(raw: dict) -> JobBase | None`
  - méthode `ThalesScraper._enrich_be_descriptions(jobs: list[JobBase]) -> list[JobBase]` (stub no-op en Task 1, implémentée en Task 2)

- [ ] **Step 1: Ajouter la valeur d'enum `THALES`**

Dans `src/models.py`, enum `JobSource`, après `ENISA = "enisa"` et avant le commentaire `# Étendu en Sprint 3+` :

```python
    ENISA = "enisa"
    THALES = "thales"
    # Étendu en Sprint 3+
    OTHER = "other"
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `tests/test_thales.py` :

```python
"""Tests ThalesScraper — Phenom SSR (phApp.ddo) + filtre BE + JSON-LD enrichment."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from src.config import SourceConfig, SourceType
from src.models import Country, JobSource
from src.scrapers.thales import ThalesScraper, _extract_ddo, _parse_posted_at, _slugify
from src.storage import JobRepository

BASE_URL = "https://careers.thalesgroup.com/global/en/search-results"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("src.scrapers.base.time.sleep", lambda *_a, **_kw: None)


@pytest.fixture
def cfg() -> SourceConfig:
    return SourceConfig(
        enabled=True,
        type=SourceType.HTML,
        base_url=BASE_URL,
        rate_limit_seconds=0.0,
        jitter_max_seconds=0.0,
        max_pages=3,
        timeout_seconds=5.0,
        max_retries=1,
        backoff_base_seconds=0.01,
        user_agent="JobHunterBot/1.0 (+test)",
        respect_robots_txt=False,
        min_hours_between_runs=0,
    )


@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "jobs.db"
    r = JobRepository(db_url=f"sqlite:///{db_path}")
    r.create_all()
    yield r
    r.engine.dispose()


def _ddo_html(jobs: list[dict], total: int) -> str:
    """Construit un HTML minimal embarquant phApp.ddo comme le vrai site."""
    import json as _json
    ddo = {"eagerLoadRefineSearch": {"totalHits": total, "data": {"jobs": jobs}}}
    return f"<html><body><script>phApp.ddo = {_json.dumps(ddo)};</script></body></html>"


BE_JOB = {
    "title": "System Engineer - Cryptographic systems",
    "reqId": "R0305314",
    "jobSeqNo": "TGPTGWGLOBALR0305314EXTERNALENGLOBAL",
    "country": "Belgium",
    "city": "Tubize",
    "state": "Walloon Brabant",
    "category": "Engineering",
    "postedDate": "2026-03-05T00:00:00.000+0000",
    "descriptionTeaser": "Short teaser with a }; tricky brace inside the string.",
    "applyUrl": "https://thales.wd3.myworkdayjobs.com/Careers/job/Tubize/x_R0305314/apply",
}
FR_JOB = {
    "title": "Architecte Cloud GCP H/F",
    "reqId": "R0305850",
    "jobSeqNo": "TGPTGWGLOBALR0305850EXTERNALENGLOBAL",
    "country": "France",
    "city": "Vélizy-Villacoublay",
    "state": "Yvelines",
    "postedDate": "2026-01-10T00:00:00.000+0000",
    "descriptionTeaser": "Poste France hors périmètre.",
}


def test_extract_ddo_handles_internal_braces():
    """raw_decode doit décoder l'objet complet même avec des `};` dans les strings."""
    html = _ddo_html([BE_JOB], total=1)
    ddo = _extract_ddo(html)
    jobs = ddo["eagerLoadRefineSearch"]["data"]["jobs"]
    assert jobs[0]["reqId"] == "R0305314"


def test_extract_ddo_missing_returns_empty():
    assert _extract_ddo("<html><body>no ddo here</body></html>") == {}


def test_slugify():
    assert _slugify("System Engineer - Cryptographic systems") == "system-engineer-cryptographic-systems"
    assert _slugify("!!!") == "job"


def test_parse_posted_at():
    assert _parse_posted_at("2026-03-05T00:00:00.000+0000") == datetime.fromisoformat(
        "2026-03-05T00:00:00.000+0000"
    )
    assert _parse_posted_at(None) is None
    assert _parse_posted_at("not-a-date") is None


@respx.mock
def test_fetch_jobs_filters_belgium_only(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([BE_JOB, FR_JOB], total=2))
    )
    scraper = ThalesScraper(cfg, repo=repo)
    jobs, has_next = scraper.fetch_jobs(1)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "R0305314"
    assert job.country == Country.BE
    assert job.company == "Thales"
    assert job.source == JobSource.THALES
    assert job.location == "Tubize, Walloon Brabant"
    assert job.url == (
        "https://careers.thalesgroup.com/global/en/job/"
        "TGPTGWGLOBALR0305314EXTERNALENGLOBAL/system-engineer-cryptographic-systems"
    )
    assert job.posted_at is not None
    assert has_next is False  # offset 0 + 10 >= total 2


@respx.mock
def test_has_next_true_when_more_pages(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([BE_JOB], total=25))
    )
    scraper = ThalesScraper(cfg, repo=repo)
    _jobs, has_next = scraper.fetch_jobs(1)
    assert has_next is True  # 0 + 10 < 25


@respx.mock
def test_empty_ddo_no_crash(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    scraper = ThalesScraper(cfg, repo=repo)
    jobs, has_next = scraper.fetch_jobs(1)
    assert jobs == []
    assert has_next is False


@respx.mock
def test_parse_job_skips_missing_fields(cfg, repo):
    broken = {"country": "Belgium", "city": "Tubize"}  # ni title ni reqId
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([broken], total=1))
    )
    scraper = ThalesScraper(cfg, repo=repo)
    jobs, _ = scraper.fetch_jobs(1)
    assert jobs == []
```

- [ ] **Step 3: Lancer les tests pour vérifier l'échec**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.scrapers.thales'`

- [ ] **Step 4: Créer `src/scrapers/thales.py`**

```python
"""Scraper Thales (careers.thalesgroup.com) — Phenom People SSR.

Le site careers Thales est une couche front Phenom. Le backend Workday
(thales.wd3.myworkdayjobs.com) est désactivé au public (redirige vers une
page de maintenance Workday), donc inutilisable. Les offres sont rendues
côté serveur et embarquées dans le HTML sous :

    phApp.ddo = { ... "eagerLoadRefineSearch": {"totalHits": N,
                       "data": {"jobs": [...]}} ... };

10 offres par page, paginées via `?from={offset}&s=1`. Aucun filtre serveur
(ni mot-clé ni pays) n'est exposé : on récupère les pages et on filtre la
Belgique côté client. Le scoring filtre le cyber en aval.

Chaque page détail (`/global/en/job/{jobSeqNo}`) expose un JSON-LD
`JobPosting` → description complète, utilisée pour enrichir les offres BE.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any, ClassVar

from loguru import logger

from src.models import Country, JobBase, JobSource
from src.scrapers.base import (
    BaseScraper,
    clean_html_to_text,
    extract_jobposting_jsonld,
)

_PAGE_SIZE = 10
_DETAIL_BASE = "https://careers.thalesgroup.com/global/en/job"
_TARGET_COUNTRY = "belgium"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _extract_ddo(html: str) -> dict[str, Any]:
    """Extrait l'objet `phApp.ddo = {...};` embarqué dans le HTML.

    Utilise `json.JSONDecoder().raw_decode` à partir de l'accolade ouvrante
    plutôt qu'une regex : robuste face aux `};` présents dans les chaînes
    JSON internes (descriptions, etc.). Retourne {} si absent ou illisible.
    """
    idx = html.find("phApp.ddo")
    if idx == -1:
        return {}
    brace = html.find("{", idx)
    if brace == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[brace:])
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug or "job"


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ThalesScraper(BaseScraper):
    """Scraper Thales via Phenom SSR (phApp.ddo) + JSON-LD enrichment."""

    name: ClassVar[str] = "thales"
    source: ClassVar[JobSource] = JobSource.THALES

    def fetch_jobs(self, page: int) -> tuple[Iterable[JobBase], bool]:
        offset = (page - 1) * _PAGE_SIZE
        url = f"{self.config.base_url}?from={offset}&s=1"
        response = self._http_get(url)

        ddo = _extract_ddo(response.text)
        els = ddo.get("eagerLoadRefineSearch") or {}
        data = els.get("data") or {}
        raw_jobs = data.get("jobs") or []
        total = els.get("totalHits") or 0

        jobs: list[JobBase] = []
        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            if (raw.get("country") or "").strip().lower() != _TARGET_COUNTRY:
                continue
            parsed = self._parse_job(raw)
            if parsed is not None:
                jobs.append(parsed)

        has_next = (offset + _PAGE_SIZE) < total
        logger.info(
            "[{}] page {} (offset {}): {} BE / {} on page (total={}, has_next={})",
            self.name, page, offset, len(jobs), len(raw_jobs), total, has_next,
        )
        jobs = self._enrich_be_descriptions(jobs)
        return jobs, has_next

    def _parse_job(self, raw: dict[str, Any]) -> JobBase | None:
        title = raw.get("title")
        req_id = raw.get("reqId")
        job_seq = raw.get("jobSeqNo")
        if not title or not req_id or not job_seq:
            return None

        city = (raw.get("city") or "").strip()
        state = (raw.get("state") or "").strip()
        location = ", ".join(p for p in (city, state) if p) or None

        url = f"{_DETAIL_BASE}/{job_seq}/{_slugify(title)}"
        teaser = raw.get("descriptionTeaser") or title

        return JobBase(
            source=JobSource.THALES,
            external_id=str(req_id),
            title=title,
            company="Thales",
            location=location,
            country=Country.BE,
            description=teaser,
            url=url,
            posted_at=_parse_posted_at(raw.get("postedDate")),
            raw_data={
                "reqId": req_id,
                "jobSeqNo": job_seq,
                "category": raw.get("category"),
                "applyUrl": raw.get("applyUrl"),
                "city": city,
                "state": state,
            },
        )

    def _enrich_be_descriptions(self, jobs: list[JobBase]) -> list[JobBase]:
        # Implémentée en Task 2.
        return jobs
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Lint/type-check**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && ruff check src/scrapers/thales.py tests/test_thales.py && mypy src/scrapers/thales.py`
Expected: pas d'erreur (corriger si besoin avant commit)

- [ ] **Step 7: Commit**

```bash
cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter
semgrep --config auto src/scrapers/thales.py
git add src/models.py src/scrapers/thales.py tests/test_thales.py
git commit -m "feat(scrapers): add Thales core scraper (Phenom SSR, BE filter)"
```

---

### Task 2: Enrichissement description via JSON-LD détail

**Files:**
- Modify: `src/scrapers/thales.py` (corps de `_enrich_be_descriptions`)
- Test: `tests/test_thales.py` (ajouts)

**Interfaces:**
- Consumes: `ThalesScraper._enrich_be_descriptions` (stub de Task 1), `extract_jobposting_jsonld`, `clean_html_to_text` (de `base.py`), `BaseScraper._http_get`.
- Produces: `_enrich_be_descriptions` remplace `job.description` par le texte nettoyé du JSON-LD si longueur ≥ 200, sinon conserve le teaser. Jamais bloquant en cas d'échec HTTP.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_thales.py` :

```python
_DETAIL_URL = (
    "https://careers.thalesgroup.com/global/en/job/"
    "TGPTGWGLOBALR0305314EXTERNALENGLOBAL/system-engineer-cryptographic-systems"
)

JSONLD_DETAIL = """
<html><body>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "JobPosting",
  "title": "System Engineer - Cryptographic systems",
  "description": "<p>You will design and validate <strong>cryptographic</strong> subsystems for secure communications.</p><ul><li>Embedded security</li><li>Key management</li><li>Penetration testing support</li></ul><p>Strong background in cybersecurity and secure hardware is required for this role in Tubize, Belgium.</p>"
}
</script>
</body></html>
"""


@respx.mock
def test_enrichment_replaces_description(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([BE_JOB], total=1))
    )
    respx.get(_DETAIL_URL).mock(return_value=httpx.Response(200, text=JSONLD_DETAIL))
    scraper = ThalesScraper(cfg, repo=repo)
    jobs, _ = scraper.fetch_jobs(1)
    assert "cryptographic" in jobs[0].description
    assert "•" in jobs[0].description  # rendu des puces
    assert "Key management" in jobs[0].description


@respx.mock
def test_enrichment_failure_keeps_teaser(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([BE_JOB], total=1))
    )
    respx.get(_DETAIL_URL).mock(return_value=httpx.Response(404))
    scraper = ThalesScraper(cfg, repo=repo)
    jobs, _ = scraper.fetch_jobs(1)
    # Teaser conservé (le `};` interne ne casse rien)
    assert "tricky brace" in jobs[0].description
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py::test_enrichment_replaces_description -v`
Expected: FAIL — `assert "cryptographic" in ...` (le stub renvoie le teaser inchangé)

- [ ] **Step 3: Implémenter `_enrich_be_descriptions`**

Remplacer le corps stub dans `src/scrapers/thales.py` :

```python
    def _enrich_be_descriptions(self, jobs: list[JobBase]) -> list[JobBase]:
        """Pour chaque offre BE, fetch la page détail et parse le JSON-LD.

        ⚠️ Ajoute 1 requête HTTP par offre BE gardée. Le rate limit du
        BaseScraper s'applique. Un échec d'enrichissement n'est jamais
        bloquant : on conserve le `descriptionTeaser` comme fallback.
        """
        for job in jobs:
            try:
                response = self._http_get(job.url)
            except Exception as e:
                logger.debug(
                    "[{}] detail fetch failed for {}: {}",
                    self.name, job.external_id, e,
                )
                continue
            posting = extract_jobposting_jsonld(response.text)
            if posting is None:
                continue
            html_desc = posting.get("description") or ""
            if html_desc:
                text = clean_html_to_text(html_desc)
                if len(text) >= 200:
                    job.description = text[:8000]
        return jobs
```

- [ ] **Step 4: Lancer tous les tests Thales**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Lint/type-check**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && ruff check src/scrapers/thales.py tests/test_thales.py && mypy src/scrapers/thales.py`
Expected: pas d'erreur

- [ ] **Step 6: Commit**

```bash
cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter
semgrep --config auto src/scrapers/thales.py
git add src/scrapers/thales.py tests/test_thales.py
git commit -m "feat(scrapers): enrich Thales BE jobs with JSON-LD descriptions"
```

---

### Task 3: Câblage — config, registre, intégration end-to-end

**Files:**
- Modify: `config/sources.yaml` (ajout entrée `thales:`)
- Modify: `src/scrapers/__init__.py` (import + `SCRAPER_FACTORIES`)
- Test: `tests/test_thales.py` (test d'intégration `run()` + test de config)

**Interfaces:**
- Consumes: `ThalesScraper` (Task 1/2), `SCRAPER_FACTORIES`, `load_sources`.
- Produces: source `"thales"` activée et résolvable par `run_scrape.py`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_thales.py` :

```python
@respx.mock
def test_run_end_to_end_persists_be_job(cfg, repo):
    respx.get(BASE_URL, params={"from": "0", "s": "1"}).mock(
        return_value=httpx.Response(200, text=_ddo_html([BE_JOB, FR_JOB], total=2))
    )
    respx.get(_DETAIL_URL).mock(return_value=httpx.Response(200, text=JSONLD_DETAIL))
    result = ThalesScraper(cfg, repo=repo).run()
    assert result.jobs_inserted == 1  # FR filtré
    assert result.aborted_reason is None
    stored = repo.get_recent_jobs(only_active=True)
    assert {j.external_id for j in stored} == {"R0305314"}


def test_registered_in_factories():
    from src.scrapers import SCRAPER_FACTORIES
    assert "thales" in SCRAPER_FACTORIES


def test_config_loads_thales():
    from src.config import load_sources
    load_sources.cache_clear()
    sources = load_sources()
    assert "thales" in sources.sources
    assert sources.sources["thales"].enabled is True
    assert sources.sources["thales"].type.value == "html"
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py::test_registered_in_factories tests/test_thales.py::test_config_loads_thales -v`
Expected: FAIL — `assert "thales" in SCRAPER_FACTORIES` et clé absente dans la config

- [ ] **Step 3: Ajouter l'entrée config**

Dans `config/sources.yaml`, dans la section `sources:` (après le bloc `enisa:` et avant `# ─── Sprint 2+ ─── planned_sources`), ajouter :

```yaml
  thales:
    enabled: true
    type: html
    base_url: "https://careers.thalesgroup.com/global/en/search-results"
    company_name_override: "Thales"
    country_default: BE
    max_pages: 330   # ~322 pages réelles (3215/10) ; arrêt naturel via has_next
    rate_limit_seconds: 3
    notes: "Phenom SSR. phApp.ddo.eagerLoadRefineSearch.data.jobs, 10/page, filtre BE client-side. Workday backend désactivé au public. Enrichissement description via JSON-LD détail."
```

- [ ] **Step 4: Enregistrer la factory**

Dans `src/scrapers/__init__.py` :

Ajouter l'import (ordre alphabétique, après `from src.scrapers.sopra_steria import SopraSteriaScraper`) :

```python
from src.scrapers.thales import ThalesScraper
```

Ajouter l'entrée au dict `SCRAPER_FACTORIES` (après la ligne `enisa`) :

```python
    "thales": ThalesScraper,                    # Sprint 3 - Thales careers (Phenom SSR, BE filter)
```

- [ ] **Step 5: Lancer toute la suite de tests**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -m pytest tests/test_thales.py -v && python -m pytest -q`
Expected: tests Thales PASS (14 tests) + suite complète verte

- [ ] **Step 6: Lint/type-check global**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && ruff check . && mypy src`
Expected: pas d'erreur

- [ ] **Step 7: Smoke test réel (1 page, dry-run)**

Run: `cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter && python -c "from src.config import load_sources; from src.scrapers.thales import ThalesScraper; c=load_sources().sources['thales']; c.max_pages=1; s=ThalesScraper(c); j,n=s.fetch_jobs(1); print('BE jobs page1:', len(j), 'has_next:', n); print([x.title for x in j])"`
Expected: s'exécute sans erreur, affiche le nombre d'offres BE de la page 1 (peut être 0 ou plus selon le catalogue du jour) et `has_next: True`

- [ ] **Step 8: Commit**

```bash
cd /Users/johan-emmanuelhatchi/Projects/Cyber-Job-Hunter
semgrep --config auto src/ config/sources.yaml
git add config/sources.yaml src/scrapers/__init__.py tests/test_thales.py
git commit -m "feat(scrapers): register Thales source + integration tests"
```

---

## Notes d'exécution

- Le smoke test réel (Task 3, Step 7) fait de vraies requêtes réseau. Si le réseau est indisponible, le sauter (les tests respx couvrent la logique).
- Couverture BE = balayage complet (`max_pages: 330`). Pour réduire le coût en test manuel, baisser temporairement `max_pages` en CLI : `python scripts/run_scrape.py --source thales --dry-run`.
- Si `mypy` se plaint du `link`/`raw` non typé, suivre le style existant (`# type: ignore[no-untyped-def]` comme dans `sopra_steria._parse_link`).
