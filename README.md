# News Coo

A Discord bot that collects news from Google News RSS feeds, organizes them by topic, and displays paginated digests using slash commands. Feed sources and topics are declared in a single YAML file; the collector builds one Google News query per topic combining all sources, fetches all topics in parallel, and fills missing top-result sources from leftover combined results or single-source fallback requests.

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

- **Declarative feed configuration.** Topics and sources are defined in `config/feeds.yaml`. Adding a new source is a two-line YAML entry (name + domain) — no code changes required. The collector builds the Google News RSS URL automatically from the topic keywords, source domains, and language.
- **Parallel collection.** All topics are fetched concurrently via `asyncio.gather`. Each topic produces a single Google News query that combines all its sources with `(site:a.com OR site:b.com)`, leveraging Google's own ranking.
- **Source coverage fallback.** The collector first keeps Google's top ranked results, then checks which configured sources are missing from that top set. Missing sources are filled from lower-ranked combined results when available, or from one individual single-source request when needed.
- **Defensive collection.** Feed configuration is validated at startup, Google News URLs are encoded from structured query parameters, RSS downloads use a timeout, transient retries, and a response-size limit.
- **Paginated Discord embeds.** The `/digest` command displays one topic per page with Previous/Next navigation buttons. The pagination component is generic and reusable by other commands.

## Requirements

- Python 3.14+
- A Discord bot token from an application invited with the `bot` and `applications.commands` scopes.
- Runtime and development dependencies listed in `requirements.txt`.

## Quick start

```bash
git clone git@github.com:JustSpica/News-coo.git
cd News-coo

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
│   └── collector.py          # RSS fetcher with parallel topics and source fallback
├── tests/
│   ├── test_collector.py     # Feed collection, parsing, ranking, fallback
│   ├── test_digest_embed.py  # Embed formatting and content
│   ├── test_feed_loader.py   # YAML loading and defaults
│   ├── test_settings.py      # Environment/config import behavior
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
| `max_articles_per_topic` | `15` | Maximum articles kept per topic after collection. Must be between `1` and `50`. |

### Topics and sources

Each topic has a `display_name`, a non-empty list of `keywords` for the search query, a supported `language` that determines the Google News locale, and a non-empty list of `sources` (name + domain). Unknown settings, unknown topic/source fields, unsupported languages, empty keywords, empty sources, and malformed domains fail fast with a configuration error. The collector combines valid entries into a single RSS URL per topic.

```yaml
topics:
  world_economy:
    display_name: "Economia Mundial"
    keywords:
      - "global economy"
      - "world markets"
      - "trade"
    language: en
    sources:
      - name: Reuters
        domain: reuters.com
      - name: Financial Times
        domain: ft.com
```

The combined Google News RSS URL follows this format:

```
https://news.google.com/rss/search?q={keyword1}+OR+{keyword2}+(site:{domain1}+OR+site:{domain2})+when:7d&hl={hl}&gl={gl}&ceid={ceid}
```

When a configured source is missing from the top results and does not appear in the lower-ranked combined results, the fallback URL targets a single source:

```
https://news.google.com/rss/search?q={keyword1}+OR+{keyword2}+site:{domain}+when:7d&hl={hl}&gl={gl}&ceid={ceid}
```

Supported languages: `en` (US locale) and `pt` (Brazilian locale). The `when:7d` suffix restricts results to the last 7 days. RSS downloads use a 30-second timeout, retry transient URL/time-out errors up to two times, and reject responses larger than 2 MB.

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
| `lint.sh` | `./_scripts/lint.sh [--check]` | Run `ruff check --fix` and `ruff format`. Pass `--check` for non-mutating validation. |
