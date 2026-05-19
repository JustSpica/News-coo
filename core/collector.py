from __future__ import annotations

import asyncio
import logging
import time
import urllib.error
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
FETCH_RETRY_ATTEMPTS = 2
FETCH_RETRY_BACKOFF_SECONDS = 0.5
MAX_FEED_BYTES = 2_000_000
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
            combined_articles = await loop.run_in_executor(None, self._fetch_topic_feed, topic)
        except Exception as exc:
            log.error("Failed to fetch topic %s: %s", topic.key, exc)
            topic_result.failed_sources = [s.name for s in topic.sources]
            return topic_result

        max_total = self._settings.max_articles_per_topic
        top_articles = combined_articles[:max_total]
        leftover = combined_articles[max_total:]

        missing_sources = self._find_missing_sources(top_articles, topic.sources)

        if not missing_sources:
            topic_result.articles = top_articles
            log.info(
                "Topic '%s': %d articles",
                topic.display_name,
                len(topic_result.articles),
            )
            return topic_result

        log.info(
            "Topic '%s': sources missing from top %d: %s",
            topic.display_name,
            max_total,
            [s.name for s in missing_sources],
        )

        replacements, failed_sources = await self._collect_source_replacements(
            topic,
            missing_sources,
            leftover,
            loop,
        )
        topic_result.failed_sources.extend(failed_sources)
        top_articles = self._replace_lowest_ranked_articles(
            top_articles,
            replacements,
            max_total,
        )

        topic_result.articles = top_articles

        log.info(
            "Topic '%s': %d articles (%d replaced)",
            topic.display_name,
            len(topic_result.articles),
            len(replacements),
        )
        return topic_result

    async def _collect_source_replacements(
        self,
        topic: Topic,
        missing_sources: list[Source],
        leftover: list[Article],
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[list[Article], list[str]]:
        replacements: list[Article] = []
        failed_sources: list[str] = []
        sources_needing_fetch: list[Source] = []

        for source in missing_sources:
            leftover_match = self._find_first_source_article(leftover, source)
            if leftover_match:
                replacements.append(leftover_match)
            else:
                sources_needing_fetch.append(source)

        if not sources_needing_fetch:
            return replacements, failed_sources

        log.info(
            "Topic '%s': fetching individually for %s",
            topic.display_name,
            [s.name for s in sources_needing_fetch],
        )
        fallback_tasks = [
            loop.run_in_executor(
                None,
                self._fetch_source_articles,
                topic,
                source,
            )
            for source in sources_needing_fetch
        ]
        results = await asyncio.gather(
            *fallback_tasks,
            return_exceptions=True,
        )

        for source, result in zip(sources_needing_fetch, results, strict=True):
            if isinstance(result, Exception):
                log.warning(
                    "Fallback fetch failed for source '%s': %s",
                    source.name,
                    result,
                )
                failed_sources.append(source.name)
                continue

            fallback_match = self._find_first_source_article(result, source)
            if fallback_match:
                replacements.append(fallback_match)
            else:
                log.warning(
                    "Fallback fetch for source '%s' returned no matching articles",
                    source.name,
                )
                failed_sources.append(source.name)

        return replacements, failed_sources

    def _fetch_topic_feed(self, topic: Topic) -> list[Article]:
        url = self._build_google_news_url(topic)
        log.info("Fetching topic '%s': %s", topic.display_name, url)
        raw_content = self._download_feed(url)
        return self._parse_feed_entries(raw_content, topic)

    def _fetch_source_articles(
        self,
        topic: Topic,
        source: Source,
    ) -> list[Article]:
        url = self._build_source_url(topic, source)
        log.info("Fetching fallback for source '%s': %s", source.name, url)
        raw_content = self._download_feed(url)
        return self._parse_feed_entries(
            raw_content,
            topic,
            limit=1,
        )

    def _parse_feed_entries(
        self,
        raw: bytes | str,
        topic: Topic,
        limit: int | None = None,
    ) -> list[Article]:
        parsed = feedparser.parse(raw)
        if parsed.bozo and not parsed.entries:
            raise parsed.bozo_exception

        articles: list[Article] = []
        for entry in parsed.entries:
            if limit is not None and len(articles) >= limit:
                break
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            source_url = getattr(entry.get("source", {}), "href", "")
            articles.append(
                Article(
                    url=link,
                    title=title,
                    source_name=self._identify_source_name(
                        source_url,
                        topic.sources,
                    ),
                    topic_key=topic.key,
                    topic_display_name=topic.display_name,
                    published_at=self._parse_date(entry),
                )
            )

        log.debug("Parsed %d entries for topic %s", len(articles), topic.key)
        return articles

    @staticmethod
    def _build_google_news_url(topic: Topic) -> str:
        keywords_part = " OR ".join(topic.keywords)
        sites_part = " OR ".join(f"site:{s.domain}" for s in topic.sources)
        return FeedCollector._build_search_url(
            f"{keywords_part} ({sites_part}) when:7d",
            topic.language,
        )

    @staticmethod
    def _build_source_url(topic: Topic, source: Source) -> str:
        keywords_part = " OR ".join(topic.keywords)
        return FeedCollector._build_search_url(
            f"{keywords_part} site:{source.domain} when:7d",
            topic.language,
        )

    @staticmethod
    def _build_search_url(query: str, language: str) -> str:
        params = {
            "q": query,
            **FeedCollector._language_params(language),
        }
        encoded_params = urllib.parse.urlencode(params, safe="():")
        return f"{GOOGLE_NEWS_RSS_BASE}?{encoded_params}"

    @staticmethod
    def _language_params(language: str) -> dict[str, str]:
        try:
            return LANGUAGE_PARAMS[language]
        except KeyError:
            supported = ", ".join(sorted(LANGUAGE_PARAMS))
            msg = f"Unsupported topic language: {language}. Supported: {supported}"
            raise ValueError(msg) from None

    @staticmethod
    def _find_missing_sources(
        articles: list[Article],
        sources: list[Source],
    ) -> list[Source]:
        found_names = {a.source_name for a in articles}
        return [s for s in sources if s.name not in found_names]

    @staticmethod
    def _find_first_source_article(articles: list[Article], source: Source) -> Article | None:
        return next((article for article in articles if article.source_name == source.name), None)

    @staticmethod
    def _replace_lowest_ranked_articles(
        top_articles: list[Article],
        replacements: list[Article],
        max_total: int,
    ) -> list[Article]:
        if not replacements:
            return top_articles
        cut = max(0, len(top_articles) - len(replacements))
        return (top_articles[:cut] + replacements)[:max_total]

    @staticmethod
    def _identify_source_name(source_url: str, sources: list[Source]) -> str:
        hostname = urllib.parse.urlparse(source_url).hostname or ""
        for source in sources:
            if hostname == source.domain or hostname.endswith(f".{source.domain}"):
                return source.name
        return "Unknown"

    @staticmethod
    def _download_feed(url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            msg = f"Unsupported URL scheme: {url}"
            raise ValueError(msg)

        for attempt in range(FETCH_RETRY_ATTEMPTS + 1):
            try:
                return FeedCollector._download_feed_once(url)
            except urllib.error.HTTPError:
                raise
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == FETCH_RETRY_ATTEMPTS:
                    raise
                log.warning("Feed download failed, retrying: %s", exc)
                time.sleep(FETCH_RETRY_BACKOFF_SECONDS * (attempt + 1))

        msg = f"Failed to download feed: {url}"
        raise RuntimeError(msg)

    @staticmethod
    def _download_feed_once(url: str) -> bytes:
        encoded_url = urllib.parse.quote(url, safe=":/?&=+%()")
        request = urllib.request.Request(encoded_url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            content = response.read(MAX_FEED_BYTES + 1)
        if len(content) > MAX_FEED_BYTES:
            msg = f"Feed response exceeded {MAX_FEED_BYTES} bytes"
            raise ValueError(msg)
        return content

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
