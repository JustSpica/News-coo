from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui.pagination import PaginationView
from config.settings import FEEDS_PATH
from core.collector import FeedCollector
from core.feed_loader import load_feeds_config
from core.models import TopicResult

EMBED_DESCRIPTION_MAX_LENGTH = 4096
MARKDOWN_ESCAPE_CHARS = set(r"\`*_{}[]()#+-.!|>~")


def build_topic_embed(
    topic_result: TopicResult,
    page_index: int,
    total_pages: int,
) -> discord.Embed:
    article_count = len(topic_result.articles)
    embed = discord.Embed(
        title=f"🗞️ {topic_result.topic_display_name} - {article_count} Artigos encontrados.",
        color=discord.Color.gold(),
    )

    description = _build_article_list(topic_result)
    embed.description = description if description else "No articles found for this topic."
    embed.set_footer(text=f"Page {page_index + 1}/{total_pages}")

    return embed


def _build_article_list(topic_result: TopicResult) -> str:
    lines: list[str] = []
    current_length = 0

    for index, article in enumerate(topic_result.articles, start=1):
        title = _escape_article_title(article.title)
        line = f"{index:02d}. **{title}**"

        if current_length + len(line) + 1 > EMBED_DESCRIPTION_MAX_LENGTH:
            break

        lines.append(line)
        current_length += len(line) + 1

    return "\n".join(lines)


def _escape_article_title(title: str) -> str:
    title = discord.utils.escape_mentions(title)
    return "".join(f"\\{char}" if char in MARKDOWN_ESCAPE_CHARS else char for char in title)


class Digest(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._settings, self._topics = load_feeds_config(FEEDS_PATH)

    @app_commands.command(description="Collect and display the latest news digest")
    async def digest(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        collector = FeedCollector(self._settings, self._topics)
        result = await collector.collect()

        non_empty_topics = [
            topic_result for topic_result in result.topic_results if topic_result.articles
        ]

        if not non_empty_topics:
            await interaction.followup.send("No articles found.")
            return

        total = len(non_empty_topics)
        pages = [
            build_topic_embed(topic_result, i, total)
            for i, topic_result in enumerate(non_empty_topics)
        ]
        view = PaginationView(pages)
        await interaction.followup.send(embed=view.current_page, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Digest(bot))
