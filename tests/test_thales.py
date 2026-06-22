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


# ─── Helpers unitaires ───────────────────────────────────────────────────


def test_extract_ddo_handles_internal_braces():
    """raw_decode doit décoder l'objet complet même avec des `};` dans les strings."""
    html = _ddo_html([BE_JOB], total=1)
    ddo = _extract_ddo(html)
    jobs = ddo["eagerLoadRefineSearch"]["data"]["jobs"]
    assert jobs[0]["reqId"] == "R0305314"


def test_extract_ddo_missing_returns_empty():
    assert _extract_ddo("<html><body>no ddo here</body></html>") == {}


def test_slugify():
    assert (
        _slugify("System Engineer - Cryptographic systems")
        == "system-engineer-cryptographic-systems"
    )
    assert _slugify("!!!") == "job"


def test_parse_posted_at():
    assert _parse_posted_at("2026-03-05T00:00:00.000+0000") == datetime.fromisoformat(
        "2026-03-05T00:00:00.000+0000"
    )
    assert _parse_posted_at(None) is None
    assert _parse_posted_at("not-a-date") is None


# ─── fetch_jobs : filtrage, pagination, robustesse ───────────────────────


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
    assert job.url == _DETAIL_URL
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


# ─── Enrichissement JSON-LD ──────────────────────────────────────────────


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


# ─── Intégration run() + câblage ─────────────────────────────────────────


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
