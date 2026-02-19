"""Publish papers to Notion database."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import TYPE_CHECKING

from notion_client import Client as NotionClient
from notion_client.errors import APIResponseError

if TYPE_CHECKING:
    from searcher import Paper

logger = logging.getLogger(__name__)

MAX_RICH_TEXT_LEN = 2000


def _truncate(text: str, limit: int = MAX_RICH_TEXT_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _build_rich_text(text: str) -> list[dict]:
    chunks = []
    while text:
        chunk, text = text[:MAX_RICH_TEXT_LEN], text[MAX_RICH_TEXT_LEN:]
        chunks.append({"text": {"content": chunk}})
    return chunks or [{"text": {"content": ""}}]


class NotionPublisher:
    def __init__(self, token: str | None = None, database_id: str | None = None):
        self.token = token or os.environ.get("NOTION_TOKEN", "")
        self.database_id = database_id or os.environ.get("NOTION_DATABASE_ID", "")
        if not self.token:
            raise ValueError("NOTION_TOKEN is required")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID is required")
        self.client = NotionClient(auth=self.token)
        # v3.0.0: Retrieve data_source_id (replaces database_id for queries/pages)
        db = self.client.databases.retrieve(database_id=self.database_id)
        self.data_source_id = db["data_sources"][0]["id"]
        logger.info(f"[Notion] data_source_id: {self.data_source_id}")

    def paper_exists(self, paper: Paper) -> bool:
        key_field = "ArXiv ID" if paper.arxiv_id else "Title"
        key_value = paper.arxiv_id if paper.arxiv_id else paper.title

        filter_prop = {
            "property": key_field,
            ("rich_text" if key_field == "ArXiv ID" else "title"): {"equals": key_value},
        }

        try:
            results = self.client.data_sources.query(
                data_source_id=self.data_source_id,
                filter=filter_prop,
            )
            return len(results.get("results", [])) > 0
        except APIResponseError as e:
            logger.warning(f"[Notion] Query failed: {e}")
            return False

    def publish_paper(self, paper: Paper) -> dict | None:
        if self.paper_exists(paper):
            logger.info(f"[Notion] Already exists: {paper.title[:50]}...")
            return None

        first_author = paper.authors[0] if paper.authors else "Unknown"
        et_al = " et al." if len(paper.authors) > 1 else ""
        aff_str = f" ({paper.affiliations[0]})" if paper.affiliations else ""
        authors_str = f"{first_author}{et_al}{aff_str}"

        properties = {
            "Title": {"title": [{"text": {"content": _truncate(paper.title, 200)}}]},
            "Authors": {"rich_text": _build_rich_text(authors_str)},
            "Venue": {"select": {"name": paper.venue or "Unknown"}},
            "Date": {"date": {"start": paper.date[:10]} if paper.date else None},
            "URL": {"url": paper.url or None},
            "ArXiv ID": {"rich_text": [{"text": {"content": paper.arxiv_id}}]},
            "Abstract (KO)": {"rich_text": _build_rich_text(paper.abstract_ko) if paper.abstract_ko else [{"text": {"content": ""}}]},
            "Novelty": {"rich_text": _build_rich_text(paper.novelty_ko)},
            "Keywords": {"multi_select": [{"name": kw} for kw in paper.keywords]},
            "Searched": {"date": {"start": date.today().isoformat()}},
        }

        if not paper.date:
            del properties["Date"]
        if not paper.url:
            del properties["URL"]

        body_blocks = []
        if paper.abstract_ko:
            body_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": "Abstract (KO)"}}]},
            })
            body_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _build_rich_text(paper.abstract_ko)},
            })

        if paper.abstract:
            body_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": "Abstract (EN)"}}]},
            })
            body_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _build_rich_text(paper.abstract)},
            })

        try:
            page = self.client.pages.create(
                parent={"data_source_id": self.data_source_id},
                properties=properties,
                children=body_blocks if body_blocks else None,
            )
            logger.info(f"[Notion] Published: {paper.title[:50]}...")
            return page
        except APIResponseError as e:
            if "rate" in str(e).lower():
                logger.warning("[Notion] Rate limited, waiting 1s...")
                time.sleep(1)
                return self.publish_paper(paper)
            logger.error(f"[Notion] Failed to publish: {e}")
            return None

    def publish_papers(self, papers: list[Paper]) -> int:
        published = 0
        for i, paper in enumerate(papers):
            logger.info(f"[Notion] Publishing {i + 1}/{len(papers)}...")
            result = self.publish_paper(paper)
            if result:
                published += 1
            time.sleep(0.35)
        return published

    @staticmethod
    def create_database(token: str, parent_page_id: str) -> str:
        client = NotionClient(auth=token)
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "Paper Tracker"}}],
            icon={"type": "emoji", "emoji": "\U0001f4c4"},
            initial_data_source={
                "properties": {
                    "Title": {"title": {}},
                    "Authors": {"rich_text": {}},
                    "Venue": {
                        "select": {
                            "options": [
                                {"name": "ArXiv", "color": "gray"},
                                {"name": "CVPR", "color": "blue"},
                                {"name": "ICCV", "color": "green"},
                                {"name": "ECCV", "color": "orange"},
                                {"name": "NeurIPS", "color": "purple"},
                                {"name": "ICML", "color": "red"},
                                {"name": "ICLR", "color": "yellow"},
                                {"name": "AAAI", "color": "pink"},
                                {"name": "CoRL", "color": "brown"},
                                {"name": "IROS", "color": "default"},
                                {"name": "ICRA", "color": "default"},
                            ]
                        }
                    },
                    "Date": {"date": {}},
                    "URL": {"url": {}},
                    "ArXiv ID": {"rich_text": {}},
                    "Abstract (KO)": {"rich_text": {}},
                    "Novelty": {"rich_text": {}},
                    "Keywords": {"multi_select": {}},
                    "Searched": {"date": {}},
                },
            },
        )
        logger.info(f"[Notion] Database created: {db['url']}")
        return db["id"]
