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
