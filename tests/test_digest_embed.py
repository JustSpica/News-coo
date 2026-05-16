from __future__ import annotations

from datetime import UTC, datetime

from bot.cogs.digest import EMBED_DESCRIPTION_MAX_LENGTH, build_topic_embed
from core.models import Article, TopicResult


def _make_article(index: int, title_length: int = 30) -> Article:
    return Article(
        url=f"https://example.com/article-{index}",
        title=f"Article title number {index:03d}" + "x" * max(0, title_length - 26),
        source_name="TestSource",
        topic_key="test_topic",
        topic_display_name="Test Topic",
        published_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )


def _make_topic_result(article_count: int = 3) -> TopicResult:
    return TopicResult(
        topic_key="test_topic",
        topic_display_name="Test Topic",
        articles=[_make_article(i) for i in range(1, article_count + 1)],
    )


class TestBuildTopicEmbed:
    def test_embed_title_contains_topic_name_and_article_count(self) -> None:
        topic_result = _make_topic_result()
        embed = build_topic_embed(topic_result, page_index=0, total_pages=3)

        assert "Test Topic" in embed.title
        assert "3 Artigos encontrados" in embed.title

    def test_embed_footer_shows_page_position(self) -> None:
        topic_result = _make_topic_result()
        embed = build_topic_embed(topic_result, page_index=2, total_pages=5)

        assert embed.footer.text == "Page 3/5"

    def test_embed_description_lists_all_articles_with_numbered_ids(self) -> None:
        topic_result = _make_topic_result(article_count=3)
        embed = build_topic_embed(topic_result, page_index=0, total_pages=1)

        assert "01." in embed.description
        assert "02." in embed.description
        assert "03." in embed.description

    def test_embed_description_contains_article_titles_in_bold(self) -> None:
        topic_result = _make_topic_result(article_count=1)
        embed = build_topic_embed(topic_result, page_index=0, total_pages=1)

        assert "**Article title" in embed.description

    def test_embed_description_never_exceeds_discord_limit(self) -> None:
        topic_result = _make_topic_result(article_count=50)
        embed = build_topic_embed(topic_result, page_index=0, total_pages=1)

        assert len(embed.description) <= EMBED_DESCRIPTION_MAX_LENGTH

    def test_empty_topic_shows_fallback_message(self) -> None:
        topic_result = TopicResult(
            topic_key="empty",
            topic_display_name="Empty Topic",
        )
        embed = build_topic_embed(topic_result, page_index=0, total_pages=1)

        assert embed.description == "No articles found for this topic."
