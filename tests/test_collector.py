from __future__ import annotations

import asyncio
import urllib.parse
from datetime import UTC, datetime

import pytest

from core.collector import MAX_FEED_BYTES, FeedCollector
from core.models import Article, FeedSettings, Source, Topic


def _build_rss(items: list[tuple[str, str, str]]) -> str:
    entries = "\n".join(
        f"    <item><title>{title}</title><link>{url}</link>"
        f'<source url="{source_url}">Source</source>'
        f"<pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate></item>"
        for title, url, source_url in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n  <channel>\n'
        f"    <title>Test</title>\n{entries}\n"
        "  </channel>\n</rss>"
    )


SAMPLE_RSS = _build_rss(
    [
        ("First Article", "https://news.google.com/article-1", "https://example.com"),
        ("Second Article", "https://news.google.com/article-2", "https://example.com"),
        ("Third Article", "https://news.google.com/article-3", "https://example.com"),
        ("Fourth Article", "https://news.google.com/article-4", "https://example.com"),
    ]
)

SAMPLE_RSS_SOURCE_A_ONLY = _build_rss(
    [
        ("A1", "https://news.google.com/a1", "https://source-a.com"),
        ("A2", "https://news.google.com/a2", "https://source-a.com"),
        ("A3", "https://news.google.com/a3", "https://source-a.com"),
        ("A4", "https://news.google.com/a4", "https://source-a.com"),
        ("A5", "https://news.google.com/a5", "https://source-a.com"),
    ]
)

SAMPLE_RSS_SOURCE_B_SINGLE = _build_rss(
    [
        ("B1", "https://news.google.com/b1", "https://source-b.com"),
    ]
)

SAMPLE_RSS_WRONG_SOURCE_SINGLE = _build_rss(
    [
        ("Wrong", "https://news.google.com/wrong", "https://wrong-source.com"),
    ]
)

SAMPLE_RSS_B_BEYOND_CUTOFF = _build_rss(
    [
        ("A1", "https://news.google.com/a1", "https://source-a.com"),
        ("A2", "https://news.google.com/a2", "https://source-a.com"),
        ("A3", "https://news.google.com/a3", "https://source-a.com"),
        ("A4", "https://news.google.com/a4", "https://source-a.com"),
        ("A5", "https://news.google.com/a5", "https://source-a.com"),
        ("B1", "https://news.google.com/b1-leftover", "https://source-b.com"),
    ]
)

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
    defaults = {"max_articles_per_topic": 15}
    defaults.update(overrides)
    return FeedSettings(**defaults)


class FakeFeedCollector(FeedCollector):
    """Substitutes network calls with canned RSS content."""

    def __init__(
        self,
        settings: FeedSettings,
        topics: list[Topic],
        rss_by_topic: dict[str, str],
        rss_by_source: dict[str, str] | None = None,
    ) -> None:
        super().__init__(settings, topics)
        self._rss_by_topic = rss_by_topic
        self._rss_by_source = rss_by_source or {}

    def _fetch_topic_feed(self, topic: Topic) -> list[Article]:
        raw = self._rss_by_topic.get(topic.key, MALFORMED_RSS)
        return self._parse_feed_entries(raw, topic)

    def _fetch_source_articles(
        self,
        topic: Topic,
        source: Source,
    ) -> list[Article]:
        raw = self._rss_by_source.get(source.domain)
        if raw is None:
            raise ConnectionError(f"No canned RSS for {source.domain}")
        return self._parse_feed_entries(raw, topic, limit=1)


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
        first = topic_result.articles[0]
        assert len(topic_result.articles) == 4
        assert first.title == "First Article"
        assert first.source_name == "TestSource"
        assert first.topic_key == "test_topic"
        assert first.topic_display_name == "Test Topic"
        assert first.published_at == datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
        assert topic_result.failed_sources == []

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


class TestArticlePrioritization:
    def test_articles_follow_google_ranking_order(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=6),
            [topic],
            {"test_topic": SAMPLE_RSS_B_BEYOND_CUTOFF},
        )
        result = asyncio.run(collector.collect())

        articles = result.topic_results[0].articles
        assert len(articles) == 6
        assert [a.title for a in articles] == ["A1", "A2", "A3", "A4", "A5", "B1"]

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
        assert result.total_articles == 8


class TestSourceFallback:
    def test_missing_source_found_in_leftover(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=4),
            [topic],
            {"test_topic": SAMPLE_RSS_B_BEYOND_CUTOFF},
        )
        result = asyncio.run(collector.collect())

        articles = result.topic_results[0].articles
        assert len(articles) == 4
        assert [a.title for a in articles] == ["A1", "A2", "A3", "B1"]
        assert result.topic_results[0].failed_sources == []

    def test_missing_source_fetched_individually(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=4),
            [topic],
            {"test_topic": SAMPLE_RSS_SOURCE_A_ONLY},
            {"source-b.com": SAMPLE_RSS_SOURCE_B_SINGLE},
        )
        result = asyncio.run(collector.collect())

        articles = result.topic_results[0].articles
        assert len(articles) == 4
        assert [a.title for a in articles] == ["A1", "A2", "A3", "B1"]
        assert result.topic_results[0].failed_sources == []

    def test_fallback_failure_records_source_as_failed(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(),
            [topic],
            {"test_topic": SAMPLE_RSS_SOURCE_A_ONLY},
        )
        result = asyncio.run(collector.collect())

        articles = result.topic_results[0].articles
        assert all(a.source_name == "SourceA" for a in articles)
        assert "SourceB" in result.topic_results[0].failed_sources

    def test_fallback_without_matching_source_records_source_as_failed(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]
        topic = _make_topic(sources=sources)
        collector = FakeFeedCollector(
            _default_settings(max_articles_per_topic=4),
            [topic],
            {"test_topic": SAMPLE_RSS_SOURCE_A_ONLY},
            {"source-b.com": SAMPLE_RSS_WRONG_SOURCE_SINGLE},
        )
        result = asyncio.run(collector.collect())

        articles = result.topic_results[0].articles
        assert [a.title for a in articles] == ["A1", "A2", "A3", "A4"]
        assert "SourceB" in result.topic_results[0].failed_sources


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
        assert "artificial+intelligence+OR+machine+learning" in url
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

    def test_unknown_language_raises_clear_error(self) -> None:
        topic = Topic(
            key="test",
            display_name="Test",
            keywords=["news"],
            language="fr",
            sources=[Source(name="Test", domain="example.com")],
        )

        with pytest.raises(ValueError, match="Unsupported topic language"):
            FeedCollector._build_google_news_url(topic)

    def test_query_values_are_url_encoded(self) -> None:
        topic = Topic(
            key="test",
            display_name="Test",
            keywords=["market & trade", "GDP=now"],
            language="en",
            sources=[Source(name="Reuters", domain="reuters.com")],
        )

        url = FeedCollector._build_google_news_url(topic)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"]

        assert query == ["market & trade OR GDP=now (site:reuters.com) when:7d"]

    def test_source_url_targets_single_domain(self) -> None:
        topic = Topic(
            key="tech",
            display_name="Tech",
            keywords=["artificial intelligence"],
            language="en",
            sources=[
                Source(name="Reuters", domain="reuters.com"),
                Source(name="WIRED", domain="wired.com"),
            ],
        )
        source = Source(name="WIRED", domain="wired.com")

        url = FeedCollector._build_source_url(topic, source)

        assert "site:wired.com" in url
        assert "site:reuters.com" not in url


class TestIdentifySourceName:
    def test_exact_domain_match(self) -> None:
        sources = [Source(name="Reuters", domain="reuters.com")]
        result = FeedCollector._identify_source_name("https://reuters.com", sources)
        assert result == "Reuters"

    def test_www_subdomain_match(self) -> None:
        sources = [Source(name="Reuters", domain="reuters.com")]
        result = FeedCollector._identify_source_name("https://www.reuters.com", sources)
        assert result == "Reuters"

    def test_subdomain_match(self) -> None:
        sources = [Source(name="Nikkei", domain="asia.nikkei.com")]
        result = FeedCollector._identify_source_name("https://asia.nikkei.com", sources)
        assert result == "Nikkei"

    def test_unknown_domain_returns_unknown(self) -> None:
        sources = [Source(name="Reuters", domain="reuters.com")]
        result = FeedCollector._identify_source_name("https://unknown.com", sources)
        assert result == "Unknown"


class TestDownloadFeed:
    def test_oversized_response_raises_clear_error(self, monkeypatch) -> None:
        class OversizedResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return None

            def read(self, _size):
                return b"x" * (MAX_FEED_BYTES + 1)

        def fake_urlopen(_request, timeout):
            return OversizedResponse()

        monkeypatch.setattr("core.collector.urllib.request.urlopen", fake_urlopen)

        with pytest.raises(ValueError, match="Feed response exceeded"):
            FeedCollector._download_feed("https://example.com/rss")
