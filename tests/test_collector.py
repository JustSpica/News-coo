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

SAMPLE_RSS_WITH_DUPLICATES = """\
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
      <title>First Article (duplicate)</title>
      <link>https://example.com/article-1</link>
      <pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/article-2</link>
      <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_RSS_MIXED_SOURCES = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>A1</title>
      <link>https://source-a.com/a1</link>
      <pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>A2</title>
      <link>https://source-a.com/a2</link>
      <pubDate>Wed, 14 May 2026 11:00:00 GMT</pubDate>
    </item>
    <item>
      <title>A3</title>
      <link>https://source-a.com/a3</link>
      <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>A4</title>
      <link>https://source-a.com/a4</link>
      <pubDate>Wed, 14 May 2026 13:00:00 GMT</pubDate>
    </item>
    <item>
      <title>B1</title>
      <link>https://source-b.com/b1</link>
      <pubDate>Wed, 14 May 2026 14:00:00 GMT</pubDate>
    </item>
    <item>
      <title>B2</title>
      <link>https://source-b.com/b2</link>
      <pubDate>Wed, 14 May 2026 15:00:00 GMT</pubDate>
    </item>
    <item>
      <title>B3</title>
      <link>https://source-b.com/b3</link>
      <pubDate>Wed, 14 May 2026 16:00:00 GMT</pubDate>
    </item>
    <item>
      <title>B4</title>
      <link>https://source-b.com/b4</link>
      <pubDate>Wed, 14 May 2026 17:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

MALFORMED_RSS = "this is not valid xml at all"


def _make_source(name: str = "TestSource", domain: str = "example.com") -> Source:
    return Source(name=name, domain=domain)


def _make_topic(
    sources: list[Source] | None = None,
    key: str = "test_topic",
) -> Topic:
    return Topic(
        key=key,
        display_name="Test Topic",
        keywords=["test", "news"],
        language="en",
        sources=sources or [_make_source()],
    )


def _default_settings(**overrides) -> FeedSettings:
    defaults = {
        "max_articles_per_topic": 15,
        "max_articles_per_source": 3,
    }
    defaults.update(overrides)
    return FeedSettings(**defaults)


class FakeFeedCollector(FeedCollector):
    """Substitutes network calls with canned RSS content keyed by topic."""

    def __init__(
        self,
        settings: FeedSettings,
        topics: list[Topic],
        rss_by_topic: dict[str, str],
    ) -> None:
        super().__init__(settings, topics)
        self._rss_by_topic = rss_by_topic

    def _fetch_topic_feed(self, topic: Topic) -> list[Article]:
        raw = self._rss_by_topic.get(topic.key, MALFORMED_RSS)
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
                    source_name=self._identify_source_name(link, topic.sources),
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
            {"test_topic": SAMPLE_RSS},
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
            {"test_topic": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        expected = datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
        assert result.topic_results[0].articles[0].published_at == expected

    def test_duplicate_urls_are_kept_only_once(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {"test_topic": SAMPLE_RSS_WITH_DUPLICATES},
        )
        result = asyncio.run(collector.collect())

        urls = [a.url for a in result.topic_results[0].articles]
        assert len(urls) == len(set(urls))

    def test_malformed_rss_records_all_sources_as_failed(self) -> None:
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
    def test_source_capped_at_max_articles_per_source(self) -> None:
        topic = _make_topic()
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_source=2),
            [topic],
            {"test_topic": SAMPLE_RSS},
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results[0].articles) == 2

    def test_topic_capped_at_max_articles_per_topic(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=5, max_articles_per_source=4),
            [topic],
            {"test_topic": SAMPLE_RSS_MIXED_SOURCES},
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results[0].articles) <= 5

    def test_multiple_topics_collect_articles_independently(self) -> None:
        topic_a = _make_topic(key="topic_a")
        topic_b = _make_topic(
            sources=[_make_source("OtherSource", "other.com")],
            key="topic_b",
        )
        collector = FakeFeedCollector(
            _default_settings(),
            [topic_a, topic_b],
            {
                "topic_a": SAMPLE_RSS,
                "topic_b": SAMPLE_RSS.replace("example.com", "other.com"),
            },
        )
        result = asyncio.run(collector.collect())

        assert len(result.topic_results) == 2
        assert result.total_articles == 6


class TestBuildGoogleNewsUrl:
    def test_english_topic_builds_correct_url(self) -> None:
        topic = Topic(
            key="tech",
            display_name="Tech",
            keywords=["artificial intelligence", "machine learning"],
            language="en",
            sources=[
                Source(name="Reuters", domain="reuters.com"),
                Source(name="WIRED", domain="wired.com"),
            ],
        )

        url = FeedCollector._build_google_news_url(topic)

        assert "news.google.com/rss/search" in url
        assert "(site:reuters.com+OR+site:wired.com)" in url
        assert "when:7d" in url
        assert "hl=en-US" in url
        assert "gl=US" in url
        assert "ceid=US:en" in url

    def test_portuguese_topic_uses_brazilian_locale(self) -> None:
        topic = Topic(
            key="economia",
            display_name="Economia",
            keywords=["economia", "mercado"],
            language="pt",
            sources=[Source(name="InfoMoney", domain="infomoney.com.br")],
        )

        url = FeedCollector._build_google_news_url(topic)

        assert "hl=pt-BR" in url
        assert "gl=BR" in url

    def test_keywords_joined_with_or(self) -> None:
        topic = Topic(
            key="test",
            display_name="Test",
            keywords=["AI", "LLM", "deep learning"],
            language="en",
            sources=[Source(name="Test", domain="example.com")],
        )

        url = FeedCollector._build_google_news_url(topic)

        assert "AI+OR+LLM+OR+deep+learning" in url

    def test_sources_grouped_in_parentheses_with_site_prefix(self) -> None:
        topic = Topic(
            key="test",
            display_name="Test",
            keywords=["news"],
            language="en",
            sources=[
                Source(name="A", domain="a.com"),
                Source(name="B", domain="b.com"),
            ],
        )

        url = FeedCollector._build_google_news_url(topic)

        assert "(site:a.com+OR+site:b.com)" in url

    def test_unknown_language_falls_back_to_english(self) -> None:
        topic = Topic(
            key="test",
            display_name="Test",
            keywords=["news"],
            language="fr",
            sources=[Source(name="Test", domain="example.com")],
        )

        url = FeedCollector._build_google_news_url(topic)

        assert "hl=en-US" in url
        assert "gl=US" in url


class TestIdentifySourceName:
    def test_exact_domain_match(self) -> None:
        sources = [Source(name="Reuters", domain="reuters.com")]
        result = FeedCollector._identify_source_name("https://reuters.com/article/1", sources)
        assert result == "Reuters"

    def test_subdomain_match(self) -> None:
        sources = [Source(name="Nikkei", domain="asia.nikkei.com")]
        result = FeedCollector._identify_source_name("https://asia.nikkei.com/article/1", sources)
        assert result == "Nikkei"

    def test_unknown_domain_returns_unknown(self) -> None:
        sources = [Source(name="Reuters", domain="reuters.com")]
        result = FeedCollector._identify_source_name("https://unknown.com/article/1", sources)
        assert result == "Unknown"
