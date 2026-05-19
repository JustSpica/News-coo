from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from core.models import FeedSettings, Source, Topic

_FEED_SETTINGS_FIELDS = {f.name for f in dataclasses.fields(FeedSettings)}


def load_feeds_config(path: Path) -> tuple[FeedSettings, list[Topic]]:
    with open(path) as yaml_file:
        raw_config = yaml.safe_load(yaml_file)

    raw_settings = raw_config.get("settings", {})
    settings = FeedSettings(**{k: v for k, v in raw_settings.items() if k in _FEED_SETTINGS_FIELDS})

    topics: list[Topic] = []
    for topic_key, topic_entry in raw_config.get("topics", {}).items():
        sources: list[Source] = []
        for source_entry in topic_entry.get("sources", []):
            sources.append(
                Source(
                    name=source_entry["name"],
                    domain=source_entry["domain"],
                )
            )
        topics.append(
            Topic(
                key=topic_key,
                display_name=topic_entry["display_name"],
                keywords=topic_entry.get("keywords", []),
                language=topic_entry.get("language", "en"),
                sources=sources,
            )
        )

    return settings, topics
