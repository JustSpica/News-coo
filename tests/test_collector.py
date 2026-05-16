from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import feedparser

from core.collector import FeedCollector
from core.models import Article, FeedSettings, Source, Topic

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>First Article</title>
      <link>https://example.com/article-1</link>
      <pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/article-2</link>
      <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Third Article</title>
      <link>https://example.com/article-3</link>
      <pubDate>Wed, 14 May 2026 14:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Fourth Article</title>
      <link>https://example.com/article-4</link>
      <pubDate>Wed, 14 May 2026 16:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

MALFORMED_RSS = "this is not valid xml at all"


def _make_source(name: str = "TestSource") -> Source:
    return Source(
        name=name,
        domain="example.com",
        google_news_url="https://news.google.com/rss/test",
    )


def _make_topic(
    sources: list[Source] | None = None,
    key: str = "test_topic",
) -> Topic:
    return Topic(
        key=key,
        display_name="Test Topic",
        sources=sources or [_make_source()],
    )


def _default_settings(**overrides) -> FeedSettings:
    defaults = {
        "max_articles_per_topic": 15,
        "max_articles_per_source": 3,
        "request_delay_seconds": 0,
    }
    defaults.update(overrides)
    return FeedSettings(**defaults)


class FakeFeedCollector(FeedCollector):
    """Substitutes network calls with canned RSS content."""

    def __init__(
        self,
        settings: FeedSettings,
        topics: list[Topic],
        rss_by_source: dict[str, str],
    ) -> None:
        super().__init__(settings, topics)
        self._rss_by_source = rss_by_source

    def _fetch_source(self, source: Source, topic: Topic) -> list[Article]:
        raw = self._rss_by_source.get(source.name, MALFORMED_RSS)
        parsed = feedparser.parse(raw)
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
        return articles


class TestFeedCollectorParsing:
    def test_valid_rss_returns_articles_with_correct_metadata(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {"TestSource": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        topic_result = result.topic_results[0]
        assert len(topic_result.articles) == 3
        assert topic_result.articles[0].title == "First Article"
        assert topic_result.articles[0].source_name == "TestSource"
        assert topic_result.articles[0].topic_key == "test_topic"
        assert topic_result.articles[0].topic_display_name == "Test Topic"
        assert topic_result.failed_sources == []

    def test_published_date_is_parsed_as_utc_datetime(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {"TestSource": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        expected = datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
        assert result.topic_results[0].articles[0].published_at == expected

    def test_duplicate_urls_across_sources_appear_only_once(self) -> None:
        sources = [_make_source("SourceA"), _make_source("SourceB")]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {"SourceA": SAMPLE_RSS, "SourceB": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        urls = [article.url for article in result.topic_results[0].articles]
        assert len(urls) == len(set(urls))

    def test_malformed_rss_records_source_as_failed_with_no_articles(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {},
        )
        result = asyncio.run(collector.collect())

        topic_result = result.topic_results[0]
        assert topic_result.articles == []
        assert "TestSource" in topic_result.failed_sources


class TestCollectorLimits:
    def test_source_returns_at_most_max_articles_per_source(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_source=2),
            [topic],
            {"TestSource": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results[0].articles) == 2

    def test_topic_returns_at_most_max_articles_per_topic(self) -> None:
        sources = [_make_source("SourceA"), _make_source("SourceB")]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=4, max_articles_per_source=3),
            [topic],
            {"SourceA": SAMPLE_RSS, "SourceB": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results[0].articles) <= 4

    def test_multiple_topics_collect_articles_independently(self) -> None:
        topic_a = _make_topic(key="topic_a")
        topic_b = _make_topic(
            sources=[_make_source("OtherSource")],
            key="topic_b",
        )
        collector = FakeFeedCollector(
            _default_settings(),
            [topic_a, topic_b],
            {"TestSource": SAMPLE_RSS, "OtherSource": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results) == 2
        assert result.total_articles == 6
