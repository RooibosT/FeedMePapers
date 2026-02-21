from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Paper:
    title: str
    authors: list[str]
    affiliations: list[str]
    abstract: str
    venue: str
    date: str
    url: str
    arxiv_id: str
    source: str

    keywords: list[str] = field(default_factory=list)
    abstract_ko: str = ""
    novelty_ko: str = ""

    def unique_key(self) -> str:
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        return f"title:{self.title.lower().strip()}"
