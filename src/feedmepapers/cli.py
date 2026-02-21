#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .llm.processor import LLMConfig, process_papers
from .models import Paper
from .notion.publisher import NotionPublisher
from .search.searcher import SearchConfig, search_papers

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_paper_summary(papers: list[Paper]) -> None:
    if not papers:
        print("\n  No papers found.\n")
        return

    print(f"\n{'='*80}")
    print(f"  Found {len(papers)} papers")
    print(f"{'='*80}\n")

    for i, p in enumerate(papers, 1):
        print(f"[{i}] {p.title}")
        first_author = p.authors[0] if p.authors else "Unknown"
        et_al = " et al." if len(p.authors) > 1 else ""
        aff_str = f" ({p.affiliations[0]})" if p.affiliations else ""
        print(f"    Author: {first_author}{et_al}{aff_str}")
        print(f"    Venue: {p.venue}  |  Date: {p.date}")
        print(f"    URL: {p.url}")

        if p.novelty_ko:
            print(f"    Novelty: {p.novelty_ko}")

        if p.abstract_ko:
            preview = p.abstract_ko[:200] + "..." if len(p.abstract_ko) > 200 else p.abstract_ko
            print(f"    Abstract(KO): {preview}")
        elif p.abstract:
            preview = p.abstract[:200] + "..." if len(p.abstract) > 200 else p.abstract
            print(f"    Abstract(EN): {preview}")

        print()


def save_json(papers: list[Paper], output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"papers_{timestamp}.json"
    data = [asdict(p) for p in papers]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Paper-AI: Recent paper search & Korean summary")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM translation/summary")
    parser.add_argument("--no-notion", action="store_true", help="Skip Notion publishing")
    parser.add_argument(
        "--setup-notion-db", metavar="PAGE_ID", help="Create Notion database under this page"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.setup_notion_db:
        token = os.environ.get("NOTION_TOKEN", "")
        if not token:
            print("Error: NOTION_TOKEN env var required. Set it in .env file.")
            sys.exit(1)
        db_id = NotionPublisher.create_database(token, args.setup_notion_db)

        env_path = Path(".env")
        if env_path.exists():
            env_text = env_path.read_text()
            if "NOTION_DATABASE_ID=" in env_text:
                import re

                env_text = re.sub(
                    r"NOTION_DATABASE_ID=.*",
                    f"NOTION_DATABASE_ID={db_id}",
                    env_text,
                )
            else:
                env_text += f"\nNOTION_DATABASE_ID={db_id}\n"
            env_path.write_text(env_text)
            print(f"\nDatabase created! NOTION_DATABASE_ID={db_id}")
            print("  → .env 파일에 자동 저장되었습니다.\n")
        else:
            print(f"\nDatabase created! Add this to your .env:\n  NOTION_DATABASE_ID={db_id}\n")
        return

    search_cfg = SearchConfig(
        keywords=cfg["keywords"],
        date_range_days=cfg.get("date_range_days", 7),
        max_results_per_keyword=cfg.get("max_results_per_keyword", 20),
        venues=cfg.get("venues") or [],
        s2_api_key=os.environ.get("S2_API_KEY", ""),
        fields_of_study=cfg.get("fields_of_study") or [],
        arxiv_categories=cfg.get("arxiv_categories") or [],
    )

    logger.info("Step 1: Searching papers...")
    papers = search_papers(search_cfg)

    if not papers:
        print("\nNo papers found for the given keywords and date range.")
        return

    logger.info(f"Found {len(papers)} unique papers.")

    if not args.no_llm:
        llm_cfg_raw = cfg.get("llm", {})
        llm_cfg = LLMConfig(
            model=llm_cfg_raw.get("model", "qwen2.5:7b"),
            base_url=os.environ.get("OLLAMA_BASE_URL") or llm_cfg_raw.get("base_url", "http://localhost:11434"),
            timeout=llm_cfg_raw.get("timeout", 120),
            temperature=llm_cfg_raw.get("temperature", 0.3),
        )
        logger.info("Step 2: LLM translation & novelty extraction...")
        papers = process_papers(llm_cfg, papers)
    else:
        logger.info("Step 2: Skipped (--no-llm)")

    output_cfg = cfg.get("output", {})
    if output_cfg.get("console", True):
        print_paper_summary(papers)

    if output_cfg.get("json_file", True):
        json_dir = output_cfg.get("json_dir", "results")
        filepath = save_json(papers, json_dir)
        logger.info(f"Saved JSON: {filepath}")

    notion_cfg = cfg.get("notion", {})
    use_notion = notion_cfg.get("enabled", False) and not args.no_notion

    if use_notion:
        logger.info("Step 3: Publishing to Notion...")
        try:
            publisher = NotionPublisher()
            count = publisher.publish_papers(papers)
            logger.info(f"Published {count} papers to Notion.")
        except ValueError as e:
            logger.error(f"Notion setup error: {e}")
            logger.info("Skipping Notion. Set up .env with NOTION_TOKEN and NOTION_DATABASE_ID.")
    else:
        logger.info("Step 3: Notion publishing disabled (set notion.enabled=true in config.yaml)")

    logger.info("Done!")


if __name__ == "__main__":
    main()
