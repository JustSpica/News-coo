from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from core.models import (
    Article,
    CollectionResult,
    FeedSettings,
    Source,
    Topic,
    TopicResult,
)

log = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30
USER_AGENT = "morgans-bot/1.0"


class FeedCollector:
    def __init__(self, settings: FeedSettings, topics: list[Topic]) -> None:
        self._settings = settings
        self._topics = topics

    async def collect(self) -> CollectionResult:
        topic_results = await asyncio.gather(
            *(self._collect_topic(topic) for topic in self._topics)
        )

        result = CollectionResult(topic_results=list(topic_results))

        log.info(
            "Collection done: %d articles across %d topics (%d source failures)",
            result.total_articles,
            len(result.topic_results),
            len(result.all_failed_sources),
        )
        return result

    async def _collect_topic(self, topic: Topic) -> TopicResult:
        topic_result = TopicResult(
            topic_key=topic.key,
            topic_display_name=topic.display_name,
        )

        seen_urls: set[str] = set()
        loop = asyncio.get_running_loop()

        for source in topic.sources:
            articles = await self._try_fetch_source(loop, source, topic)
            if articles is None:
                topic_result.failed_sources.append(source.name)
                continue

            self._append_deduplicated(topic_result, articles, seen_urls)

            max_per_topic = self._settings.max_articles_per_topic
            if len(topic_result.articles) >= max_per_topic:
                topic_result.articles = topic_result.articles[:max_per_topic]
                break

            await asyncio.sleep(self._settings.request_delay_seconds)

        log.info(
            "Topic '%s': %d articles, %d failed sources",
            topic.display_name,
            len(topic_result.articles),
            len(topic_result.failed_sources),
        )
        return topic_result

    async def _try_fetch_source(
        self,
        loop: asyncio.AbstractEventLoop,
        source: Source,
        topic: Topic,
    ) -> list[Article] | None:
        try:
            return await loop.run_in_executor(
                None,
                self._fetch_source,
                source,
                topic,
            )
        except Exception as exc:
            log.error("Failed source %s in topic %s: %s", source.name, topic.key, exc)
            return None

    def _append_deduplicated(
        self,
        topic_result: TopicResult,
        articles: list[Article],
        seen_urls: set[str],
    ) -> None:
        source_count = 0
        for article in articles:
            if article.url in seen_urls:
                continue
            if source_count >= self._settings.max_articles_per_source:
                break
            seen_urls.add(article.url)
            topic_result.articles.append(article)
            source_count += 1

    def _fetch_source(self, source: Source, topic: Topic) -> list[Article]:
        raw_content = self._download_feed(source.google_news_url)

        parsed = feedparser.parse(raw_content)

        if parsed.bozo and not parsed.entries:
            raise parsed.bozo_exception

        articles: list[Article] = []
        for entry in parsed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue

            articles.append(
                Article(
                    url=link,
                    title=title,
                    source_name=source.name,
                    topic_key=topic.key,
                    topic_display_name=topic.display_name,
                    published_at=self._parse_date(entry),
                )
            )

        log.debug("Parsed %d entries from %s", len(articles), source.name)
        return articles

    @staticmethod
    def _download_feed(url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            msg = f"Unsupported URL scheme: {url}"
            raise ValueError(msg)
        encoded_url = urllib.parse.quote(url, safe=":/?&=+%")
        request = urllib.request.Request(encoded_url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.read()

    @staticmethod
    def _parse_date(entry: dict) -> datetime | None:
        for date_field in ("published", "updated"):
            raw = entry.get(date_field)
            if not raw:
                continue
            try:
                return parsedate_to_datetime(raw).astimezone(UTC)
            except ValueError, TypeError:
                continue
        return None
