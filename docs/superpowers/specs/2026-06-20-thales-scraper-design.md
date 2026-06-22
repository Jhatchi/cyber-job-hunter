# Scraper Thales (careers.thalesgroup.com) — Design

Date : 2026-06-20
Source cible : https://careers.thalesgroup.com/global/en/search-results

## Contexte

Ajout d'une source au projet Cyber-Job-Hunter : les offres Thales, gros
employeur cyber/defense avec presence en Belgique (Tubize, Herstal). Le
scraper doit s'integrer aux patterns existants (BaseScraper, scoring, storage)
sans introduire de nouvelle dependance.

## Reconnaissance (faits etablis)

- **ATS = Phenom People.** Le site careers est la couche front Phenom.
- **Backend Workday desactive au public.** `thales.wd3.myworkdayjobs.com`
  redirige vers une page de maintenance Workday. Le pattern Workday du projet
  (WorkdayScraper) n'est donc PAS utilisable ici.
- **Seule source fiable : le HTML rendu cote serveur (SSR).** Chaque page
  embarque les offres dans `phApp.ddo.eagerLoadRefineSearch.data.jobs`.
- **Pagination** via query param `?from=N&s=1` : 10 offres par page,
  **3215 offres au total** (champ `totalHits`).
- **Aucun filtre serveur accessible** : ni mot-cle ni pays via l'URL.
  L'API JSON `/widgets` (ddoKey `refineSearch`) renvoie les compteurs filtres
  (2203 pour "cyber") mais **jamais les bodies d'offres**, meme avec session +
  token CSRF + headers navigateur (anti-scrape volontaire).
- **Taille de page verrouillee a 10** : les params `size`/`pageSize`/`rows`
  sont ignores. Le nombre de requetes pour un balayage complet est donc
  incompressible (~322 requetes).
- **Ordre fixe mais arbitraire** (pas trie par date). La Belgique est
  dispersee sur l'ensemble des pages.
- **URL de detail** : `https://careers.thalesgroup.com/global/en/job/{jobSeqNo}`
  renvoie HTTP 200 et contient du JSON-LD `JobPosting` (description complete).
- **robots.txt** : n'interdit ni `/search-results` ni `/job/`
  (seul `*/jobcart` et quelques chemins applicatifs `/apply`, `/px-widgets`...
  sont en Disallow). Le scraper respecte robots via `BaseScraper._robots_allowed`.

## Decisions

- **Perimetre geographique : Belgique uniquement** (`country == "Belgium"`).
  Filtrage cote client apres parsing.
- **Profondeur : crawl complet (~322 pages).** `max_pages: 330` en config,
  arret naturel via `has_next` quand `from + 10 >= totalHits`. ~16-20 min/run,
  une fois par 12h (`min_hours_between_runs`).
- **Cyber : non filtre dans le scraper.** Le `scoring` filtre la pertinence
  cyber apres coup, comme pour toutes les autres sources.
- **Description : enrichie pour les offres BE gardees uniquement**, depuis le
  JSON-LD `JobPosting` de la page detail (helper `extract_jobposting_jsonld`
  deja present dans `base.py`). Le `descriptionTeaser` embarque sert de fallback.

## Architecture

### 1. `src/scrapers/thales.py` — `ThalesScraper(BaseScraper)`

- `name = "thales"`, `source = JobSource.THALES`
- `fetch_jobs(page) -> tuple[list[JobBase], bool]` :
  1. `offset = (page - 1) * 10`
  2. `GET {base_url}?from={offset}&s=1`
  3. Extraction robuste de `phApp.ddo` : localiser `phApp.ddo =` puis
     `json.JSONDecoder().raw_decode(...)` a partir de l'accolade ouvrante
     (pas de regex greedy/non-greedy fragile).
  4. Lire `eagerLoadRefineSearch.data.jobs` (liste) et `eagerLoadRefineSearch.totalHits`.
  5. Ne garder que les offres `country == "Belgium"` -> `_parse_job`.
  6. `has_next = (offset + 10) < totalHits`.
  7. Enrichir les offres BE gardees via `_enrich_be_descriptions` (JSON-LD).
  8. Retourner `(be_jobs, has_next)`.
- `_parse_job(raw: dict) -> JobBase | None` :
  - `external_id = raw["reqId"]` (ex. `R0304793`)
  - `title = raw["title"]`, `company = "Thales"`, `country = Country.BE`
  - `location` = composition de `city` + `state` (champs disponibles)
  - `url = f"https://careers.thalesgroup.com/global/en/job/{jobSeqNo}/{slug}"`
    ou `slug` = titre slugifie (l'URL fonctionne aussi sans slug ; le slug
    est ajoute pour la lisibilite humaine)
  - `description = raw.get("descriptionTeaser", "")` (enrichie ensuite)
  - `posted_at` = parse de `raw["postedDate"]` (ISO 8601, ex.
    `2026-03-05T00:00:00.000+0000`) ; `None` si parsing echoue
  - `raw_data` = `{reqId, jobSeqNo, category, applyUrl, city, state, country}`
  - Retourne `None` si `title` ou `reqId` manquant (offre ignoree).
- `_enrich_be_descriptions(jobs) -> list[JobBase]` : pour chaque offre BE,
  `_http_get(job.url)`, `extract_jobposting_jsonld`, `clean_html_to_text` sur
  `description`, remplace si longueur >= seuil. Echec d'enrichissement =
  on garde le teaser (jamais bloquant).

### 2. `src/models.py`

- Ajouter `THALES = "thales"` a l'enum `JobSource`.

### 3. `config/sources.yaml`

```yaml
  thales:
    enabled: true
    type: html
    base_url: "https://careers.thalesgroup.com/global/en/search-results"
    company_name_override: "Thales"
    country_default: BE
    max_pages: 330   # ~322 pages reelles (3215/10) ; arret via has_next
    rate_limit_seconds: 3
    notes: "Phenom SSR. phApp.ddo.eagerLoadRefineSearch.data.jobs, 10/page, filtre BE client-side. Workday backend desactive au public. Enrichissement description via JSON-LD detail."
```

### 4. `src/scrapers/__init__.py`

- `from src.scrapers.thales import ThalesScraper`
- `SCRAPER_FACTORIES["thales"] = ThalesScraper`

### 5. `tests/test_thales.py`

Tests sur fixture HTML statique (aucun reseau), suivant `test_sopra_steria` /
`test_workday` :

- Parsing : une fixture avec offres BE + non-BE, assert que seules les BE sont
  retournees et que les champs (`title`, `external_id`, `url`, `country`,
  `posted_at`) sont corrects.
- `has_next` : True quand `offset + 10 < totalHits`, False sinon.
- Construction d'URL detail (format `/job/{jobSeqNo}/...`).
- Robustesse extraction `phApp.ddo` (JSON contenant des `};` internes).
- HTML sans bloc `phApp.ddo` -> retourne `([], False)` sans crash.

## Hors-perimetre (YAGNI)

- Pas de filtrage cyber dans le scraper (delegue au scoring).
- Pas de support multi-pays (BE seulement ; extensible plus tard si besoin).
- Pas d'usage de l'API `/widgets` (ne livre pas les offres).
- Pas de scraping du backend Workday (desactive).

## Limites assumees

- Couverture dependante du balayage complet : si `max_pages` est reduit, la
  couverture BE devient partielle (offres BE dispersees, ordre non-date).
- ~322 requetes/run : volume atypique vs les autres scrapers (1-5 pages), mais
  borne a 1 run / 12h et avec rate limit + jitter.
