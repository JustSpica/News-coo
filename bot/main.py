import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import DISCORD_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("news-coo-bot")

intents = discord.Intents.default()

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready() -> None:
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s)", len(synced))
    except discord.HTTPException:
        log.exception("Failed to sync slash commands")

    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


async def load_cogs() -> None:
    cogs_dir = Path(__file__).parent / "cogs"
    for filepath in sorted(cogs_dir.glob("*.py")):
        if filepath.name.startswith("_"):
            continue
        cog_module = f"bot.cogs.{filepath.stem}"
        await bot.load_extension(cog_module)
        log.info("Loaded cog: %s", cog_module)


async def main() -> None:
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
