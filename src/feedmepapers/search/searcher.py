"""Paper search via Semantic Scholar API + arxiv API."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests

from ..models import Paper

logger = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = (
    "title,abstract,authors.name,authors.affiliations,venue,year,"
    "publicationDate,externalIds,url,openAccessPdf"
)
ARXIV_API = "http://export.arxiv.org/api/query"

@dataclass
class SearchConfig:
    keywords: list  # str (single) or list[str] (AND combination)
    date_range_days: int = 7
    max_results_per_keyword: int = 20
    venues: list[str] = field(default_factory=list)
    s2_api_key: str = ""
    fields_of_study: list[str] = field(default_factory=list)
    arxiv_categories: list[str] = field(default_factory=list)


def _normalize_keyword(entry) -> tuple[str, str, list[str], str]:
    """Return (s2_query, arxiv_query, keyword_tags, display_name)."""
    if isinstance(entry, list):
        terms = [str(t) for t in entry if t]
        if not terms:
            return "", "", [], ""
        s2_query = " ".join(f'"{t}"' for t in terms)
        arxiv_parts = [f'(ti:"{t}" OR abs:"{t}")' for t in terms]
        arxiv_query = " AND ".join(arxiv_parts)
        return s2_query, arxiv_query, list(terms), " + ".join(terms)
    kw = str(entry)
    return kw, f'(ti:"{kw}" OR abs:"{kw}")', [kw], kw


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _parse_s2_authors(authors_raw: list[dict]) -> tuple[list[str], list[str]]:
    names, affiliations = [], []
    for a in authors_raw:
        name = a.get("name", "")
        if name:
            names.append(name)
        affs = a.get("affiliations") or []
        for aff in affs:
            if aff and aff not in affiliations:
                affiliations.append(aff)
    return names, affiliations


def search_semantic_scholar(cfg: SearchConfig) -> list[Paper]:
    start_date, end_date = _date_range(cfg.date_range_days)
    date_filter = f"{start_date}:{end_date}"
    papers: list[Paper] = []
    headers = {}
    if cfg.s2_api_key:
        headers["X-API-KEY"] = cfg.s2_api_key

    for kw_entry in cfg.keywords:
        s2_query, _, keyword_tags, display = _normalize_keyword(kw_entry)
        if not s2_query:
            continue
        logger.info(f"[S2] Searching: '{display}' ({start_date} ~ {end_date})")

        params: dict = {
            "query": s2_query,
            "limit": cfg.max_results_per_keyword,
            "fields": S2_FIELDS,
            "publicationDateOrYear": date_filter,
        }
        if cfg.fields_of_study:
            params["fieldsOfStudy"] = ",".join(cfg.fields_of_study)

        resp = None
        for attempt in range(4):
            try:
                resp = requests.get(
                    f"{S2_BASE}/paper/search",
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code == 429:
                    wait = 2**attempt + 1
                    logger.warning(
                        f"[S2] Rate limited, waiting {wait}s (attempt {attempt + 1}/4)..."
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                logger.error(f"[S2] Request failed for '{display}': {e}")
                resp = None
                break

        if resp is None or resp.status_code != 200:
            logger.warning(f"[S2] Skipping '{display}' after retries")
            continue

        data = resp.json()
        total = data.get("total", 0)
        logger.info(f"[S2] Found {total} results for '{display}'")

        for item in data.get("data") or []:
            if not item.get("title") or not item.get("abstract"):
                continue

            venue = item.get("venue") or ""
            if cfg.venues and venue:
                venue_lower = venue.lower()
                if not any(v.lower() in venue_lower for v in cfg.venues):
                    continue

            names, affs = _parse_s2_authors(item.get("authors") or [])

            ext_ids = item.get("externalIds") or {}
            arxiv_id = ext_ids.get("ArXiv") or ""
            paper_url = item.get("url") or ""
            if arxiv_id and not paper_url:
                paper_url = f"https://arxiv.org/abs/{arxiv_id}"

            papers.append(
                Paper(
                    title=item["title"],
                    authors=names,
                    affiliations=affs,
                    abstract=item["abstract"],
                    venue=venue,
                    date=item.get("publicationDate") or str(item.get("year") or ""),
                    url=paper_url,
                    arxiv_id=arxiv_id,
                    source="semantic_scholar",
                    keywords=list(keyword_tags),
                )
            )

        if not cfg.s2_api_key:
            time.sleep(1.1)

    return papers


def search_arxiv(cfg: SearchConfig) -> list[Paper]:
    papers: list[Paper] = []
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    cat_filter = ""
    if cfg.arxiv_categories:
        cat_parts = " OR ".join(f"cat:{c}" for c in cfg.arxiv_categories)
        cat_filter = f" AND ({cat_parts})"

    for kw_entry in cfg.keywords:
        _, arxiv_query, keyword_tags, display = _normalize_keyword(kw_entry)
        if not arxiv_query:
            continue
        logger.info(f"[arxiv] Searching: '{display}'")

        params = {
            "search_query": arxiv_query + cat_filter,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": cfg.max_results_per_keyword,
        }

        try:
            resp = requests.get(ARXIV_API, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"[arxiv] Request failed for '{display}': {e}")
            continue

        root = ET.fromstring(resp.text)
        cutoff = datetime.now() - timedelta(days=cfg.date_range_days)

        for entry in root.findall("atom:entry", ns):
            published = entry.findtext("atom:published", "", ns)
            if published:
                pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_date.replace(tzinfo=None) < cutoff:
                    continue

            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")

            if not title or not abstract:
                continue

            if cfg.venues:
                categories = [
                    c.get("term", "") for c in entry.findall("arxiv:primary_category", ns)
                ]
                categories += [c.get("term", "") for c in entry.findall("atom:category", ns)]
                cat_str = " ".join(categories).lower()
                venue_matched = any(v.lower() in cat_str for v in cfg.venues) or "arxiv" in [
                    v.lower() for v in cfg.venues
                ]
                if not venue_matched:
                    continue

            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            affiliations = []
            for a in entry.findall("atom:author", ns):
                aff = a.findtext("arxiv:affiliation", "", ns)
                if aff and aff not in affiliations:
                    affiliations.append(aff)

            link = ""
            for l in entry.findall("atom:link", ns):
                if l.get("type") == "text/html" or l.get("rel") == "alternate":
                    link = l.get("href", "")
                    break

            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            date_str = published[:10] if published else ""

            papers.append(
                Paper(
                    title=title,
                    authors=authors,
                    affiliations=affiliations,
                    abstract=abstract,
                    venue="arxiv",
                    date=date_str,
                    url=link or f"https://arxiv.org/abs/{arxiv_id}",
                    arxiv_id=arxiv_id,
                    source="arxiv",
                    keywords=list(keyword_tags),
                )
            )

        time.sleep(0.5)

    return papers


def search_papers(cfg: SearchConfig) -> list[Paper]:
    s2_papers = search_semantic_scholar(cfg)
    arxiv_papers = search_arxiv(cfg)
    merged = merge_unique_papers(s2_papers + arxiv_papers)

    logger.info(
        f"[search] Total unique papers: {len(merged)} (S2: {len(s2_papers)}, arxiv: {len(arxiv_papers)})"
    )
    return merged


def merge_unique_papers(papers: list[Paper]) -> list[Paper]:
    seen: dict[str, Paper] = {}
    merged: list[Paper] = []

    for p in papers:
        key = p.unique_key()
        if key not in seen:
            seen[key] = p
            merged.append(p)
        else:
            # Merge keywords from duplicate
            for kw in p.keywords:
                if kw not in seen[key].keywords:
                    seen[key].keywords.append(kw)

    merged.sort(key=lambda p: p.date, reverse=True)
    return merged
