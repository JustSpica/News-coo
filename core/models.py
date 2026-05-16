from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FeedSettings:
    max_articles_per_topic: int = 10
    max_articles_per_source: int = 3
    request_delay_seconds: float = 0.5


@dataclass(frozen=True)
class Source:
    name: str
    domain: str
    google_news_url: str


@dataclass(frozen=True)
class Topic:
    key: str
    display_name: str
    sources: list[Source]


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    source_name: str
    topic_key: str
    topic_display_name: str
    published_at: datetime | None = None


@dataclass
class TopicResult:
    topic_key: str
    topic_display_name: str
    articles: list[Article] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)


@dataclass
class CollectionResult:
    topic_results: list[TopicResult] = field(default_factory=list)

    @property
    def total_articles(self) -> int:
        return sum(len(topic_result.articles) for topic_result in self.topic_results)

    @property
    def all_failed_sources(self) -> list[str]:
        return [
            source_name
            for topic_result in self.topic_results
            for source_name in topic_result.failed_sources
        ]
