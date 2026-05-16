# News Coo

A Discord bot that collects news from Google News RSS feeds, organizes them by topic, and displays paginated digests using slash commands. Feed sources and topics are declared in a single YAML file; the collector fetches all topics in parallel with per-source rate limiting and cross-source deduplication.

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Configuration](#configuration)
  - [Settings](#settings)
  - [Topics and sources](#topics-and-sources)
- [Usage](#usage)
- [Scripts](#scripts)

## Features

- **Declarative feed configuration.** Topics and sources are defined in `config/feeds.yaml`. Adding a new source is a three-line YAML entry — no code changes required.
- **Parallel collection.** All topics are fetched concurrently via `asyncio.gather`, with a configurable delay between sources within each topic to respect rate limits.
- **Cross-source deduplication.** Duplicate articles (by URL) within the same topic are filtered out automatically.
- **Paginated Discord embeds.** The `/digest` command displays one topic per page with Previous/Next navigation buttons. The pagination component is generic and reusable by other commands.
- **Per-source and per-topic limits.** Configurable caps prevent any single source from dominating a topic and keep each topic to a manageable article count.

## Requirements

- Python 3.14+
- A Discord bot token with the Message Content intent enabled.
- Dependencies listed in `requirements.txt` (discord.py, feedparser, PyYAML, python-dotenv).

## Quick start

```bash
git clone git@github.com:JustSpica/News-coo.git
cd news-coo-bot

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set DISCORD_TOKEN=your-bot-token

./_scripts/setup.sh up
```

The bot logs to `bot.log` in the project root. Use `./_scripts/setup.sh status` to check if it is running.

## Project layout

```text
.
├── _scripts/
│   ├── setup.sh              # Bot process management (up/down/restart/status)
│   ├── test.sh               # Runs pytest
│   └── lint.sh               # Runs ruff check --fix + ruff format
├── bot/
│   ├── main.py               # Bot entrypoint, cog loader, logging setup
│   ├── cogs/
│   │   └── digest.py         # /digest command and topic embed builder
│   └── ui/
│       └── pagination.py     # Reusable paginated embed view
├── config/
│   ├── settings.py           # Environment variables and path constants
│   └── feeds.yaml            # Topic and source declarations
├── core/
│   ├── models.py             # Domain dataclasses (Article, Topic, Source, etc.)
│   ├── feed_loader.py        # YAML config parser
│   └── collector.py          # RSS fetcher with parallel topics and dedup
├── tests/
│   ├── test_collector.py     # Feed collection, parsing, limits, dedup
│   ├── test_digest_embed.py  # Embed formatting and content
│   ├── test_feed_loader.py   # YAML loading and defaults
│   └── test_pagination.py    # Pagination view navigation and state
├── .env.example              # Template for environment variables
├── ruff.toml                 # Linter and formatter configuration
└── requirements.txt          # Pinned Python dependencies
```

`core/` contains domain logic with no dependency on Discord. `bot/` is the Discord interface layer that consumes `core/`. `config/` centralizes all configuration.

## Configuration

### Settings

`config/feeds.yaml` accepts a top-level `settings` key with the following options:

| Key | Default | Description |
|---|---|---|
| `max_articles_per_topic` | `15` | Maximum articles kept per topic after collection. |
| `max_articles_per_source` | `3` | Maximum articles accepted from a single source within a topic. |
| `request_delay_seconds` | `0.5` | Delay in seconds between source fetches within the same topic. |

### Topics and sources

Each topic has a `display_name` and a list of `sources`. Each source points to a Google News RSS search URL filtered by `site:` and search terms.

```yaml
topics:
  economia_mundial:
    display_name: "Economia Mundial"
    sources:
      - name: Reuters
        domain: reuters.com
        google_news: "https://news.google.com/rss/search?q=global+economy+site:reuters.com+when:7d&hl=en-US&gl=US&ceid=US:en"
```

The Google News RSS URL format is:

```
https://news.google.com/rss/search?q={query}&hl={lang}&gl={country}&ceid={country}:{lang_code}
```

The `when:7d` suffix in the query restricts results to the last 7 days.

## Usage

Once the bot is running and has synced its slash commands:

```
/digest
```

The bot defers the response, fetches all configured topics in parallel, and replies with a paginated embed. Each page shows one topic with its articles listed in bold. Use the **◀ Previous** and **Next ▶** buttons to navigate between topics.

## Scripts

All scripts are in `_scripts/` and activate the virtual environment automatically.

| Script | Usage | Description |
|---|---|---|
| `setup.sh` | `./_scripts/setup.sh up\|down\|restart\|status` | Manage the bot process (background, PID file, logs to `bot.log`). |
| `test.sh` | `./_scripts/test.sh [-v]` | Run the test suite. Accepts any pytest arguments. |
| `lint.sh` | `./_scripts/lint.sh [--check]` | Run `ruff check --fix` and `ruff format`. Pass `--check` to verify without modifying files. |
