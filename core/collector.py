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
USER_AGENT = "news-coo/1.0"
GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"

LANGUAGE_PARAMS: dict[str, dict[str, str]] = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "pt": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
}


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

        loop = asyncio.get_running_loop()
        try:
            articles = await loop.run_in_executor(
                None, self._fetch_topic_feed, topic
            )
        except Exception as exc:
            log.error("Failed to fetch topic %s: %s", topic.key, exc)
            topic_result.failed_sources = [s.name for s in topic.sources]
            return topic_result

        topic_result.articles = self._prioritize_articles(articles)

        log.info(
            "Topic '%s': %d articles",
            topic.display_name,
            len(topic_result.articles),
        )
        return topic_result

    def _prioritize_articles(self, articles: list[Article]) -> list[Article]:
        min_per_source = self._settings.min_articles_per_source
        max_per_topic = self._settings.max_articles_per_topic

        guaranteed: list[Article] = []
        remaining: list[Article] = []
        source_counts: dict[str, int] = {}
        seen_urls: set[str] = set()

        for article in articles:
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)

            count = source_counts.get(article.source_name, 0)
            if count < min_per_source:
                guaranteed.append(article)
                source_counts[article.source_name] = count + 1
            else:
                remaining.append(article)

        result = guaranteed[:]
        slots_left = max_per_topic - len(result)
        if slots_left > 0:
            result.extend(remaining[:slots_left])

        return result[:max_per_topic]

    def _fetch_topic_feed(self, topic: Topic) -> list[Article]:
        url = self._build_google_news_url(topic)
        raw_content = self._download_feed(url)

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
                    source_name=self._identify_source_name(link, topic.sources),
                    topic_key=topic.key,
                    topic_display_name=topic.display_name,
                    published_at=self._parse_date(entry),
                )
            )

        log.debug("Parsed %d entries for topic %s", len(articles), topic.key)
        return articles

    @staticmethod
    def _build_google_news_url(topic: Topic) -> str:
        keywords_part = "+OR+".join(k.replace(" ", "+") for k in topic.keywords)
        sites_part = "+OR+".join(f"site:{s.domain}" for s in topic.sources)
        query = f"{keywords_part}+({sites_part})+when:7d"
        lang_params = LANGUAGE_PARAMS.get(topic.language, LANGUAGE_PARAMS["en"])
        params = "&".join(f"{k}={v}" for k, v in lang_params.items())
        return f"{GOOGLE_NEWS_RSS_BASE}?q={query}&{params}"

    @staticmethod
    def _identify_source_name(article_url: str, sources: list[Source]) -> str:
        hostname = urllib.parse.urlparse(article_url).hostname or ""
        for source in sources:
            if hostname == source.domain or hostname.endswith(f".{source.domain}"):
                return source.name
        return "Unknown"

    @staticmethod
    def _download_feed(url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            msg = f"Unsupported URL scheme: {url}"
            raise ValueError(msg)
        encoded_url = urllib.parse.quote(url, safe=":/?&=+%()")
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
            except (ValueError, TypeError):
                continue
        return None
