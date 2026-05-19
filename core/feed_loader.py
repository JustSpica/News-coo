from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from core.models import SUPPORTED_TOPIC_LANGUAGES, FeedSettings, Source, Topic

_FEED_SETTINGS_FIELDS = {f.name for f in dataclasses.fields(FeedSettings)}
_DEFAULT_FEED_SETTINGS = FeedSettings()
_MAX_ARTICLES_PER_TOPIC_LIMIT = 50
_TOPIC_FIELDS = {"display_name", "keywords", "language", "sources"}
_SOURCE_FIELDS = {"name", "domain"}
_DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class FeedConfigError(ValueError):
    """Raised when the feeds YAML file has an invalid shape or value."""


def load_feeds_config(path: Path) -> tuple[FeedSettings, list[Topic]]:
    with path.open(encoding="utf-8") as yaml_file:
        raw_config = yaml.safe_load(yaml_file)

    config = _require_mapping(raw_config, "feeds config")
    settings = _load_settings(config.get("settings", {}))
    topics = _load_topics(config.get("topics", {}))

    return settings, topics


def _load_settings(raw_settings: object) -> FeedSettings:
    settings = _require_mapping({} if raw_settings is None else raw_settings, "settings")
    unknown_settings = sorted(set(settings) - _FEED_SETTINGS_FIELDS)
    if unknown_settings:
        msg = f"Unknown feed setting(s): {', '.join(unknown_settings)}"
        raise FeedConfigError(msg)

    max_articles = _validate_max_articles_per_topic(
        settings.get(
            "max_articles_per_topic",
            _DEFAULT_FEED_SETTINGS.max_articles_per_topic,
        )
    )
    return FeedSettings(max_articles_per_topic=max_articles)


def _load_topics(raw_topics: object) -> list[Topic]:
    topics_mapping = _require_mapping({} if raw_topics is None else raw_topics, "topics")

    topics: list[Topic] = []
    for topic_key, raw_topic_entry in topics_mapping.items():
        if not isinstance(topic_key, str) or not topic_key:
            msg = "Topic keys must be non-empty strings"
            raise FeedConfigError(msg)

        topic_entry = _require_mapping(raw_topic_entry, f"topic '{topic_key}'")
        unknown_fields = sorted(set(topic_entry) - _TOPIC_FIELDS)
        if unknown_fields:
            msg = f"Unknown field(s) in topic '{topic_key}': {', '.join(unknown_fields)}"
            raise FeedConfigError(msg)

        language = _require_non_empty_string(
            topic_entry.get("language", "en"),
            f"topic '{topic_key}' language",
        )
        if language not in SUPPORTED_TOPIC_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_TOPIC_LANGUAGES))
            msg = (
                f"Unsupported language for topic '{topic_key}': {language}. Supported: {supported}"
            )
            raise FeedConfigError(msg)

        topics.append(
            Topic(
                key=topic_key,
                display_name=_require_non_empty_string(
                    topic_entry.get("display_name"),
                    f"topic '{topic_key}' display_name",
                ),
                keywords=_require_string_list(
                    topic_entry.get("keywords"),
                    f"topic '{topic_key}' keywords",
                ),
                language=language,
                sources=_load_sources(topic_key, topic_entry.get("sources")),
            )
        )
    return topics


def _load_sources(topic_key: str, raw_sources: object) -> list[Source]:
    if not isinstance(raw_sources, list) or not raw_sources:
        msg = f"topic '{topic_key}' sources must be a non-empty list"
        raise FeedConfigError(msg)

    sources: list[Source] = []
    for index, raw_source in enumerate(raw_sources, start=1):
        source_entry = _require_mapping(raw_source, f"topic '{topic_key}' source #{index}")
        unknown_fields = sorted(set(source_entry) - _SOURCE_FIELDS)
        if unknown_fields:
            msg = (
                f"Unknown field(s) in topic '{topic_key}' source #{index}: "
                f"{', '.join(unknown_fields)}"
            )
            raise FeedConfigError(msg)

        domain = _require_non_empty_string(
            source_entry.get("domain"),
            f"topic '{topic_key}' source #{index} domain",
        )
        if (
            not _DOMAIN_PATTERN.fullmatch(domain)
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            msg = f"topic '{topic_key}' source #{index} domain is invalid: {domain}"
            raise FeedConfigError(msg)

        sources.append(
            Source(
                name=_require_non_empty_string(
                    source_entry.get("name"),
                    f"topic '{topic_key}' source #{index} name",
                ),
                domain=domain,
            )
        )
    return sources


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{label} must be a mapping"
        raise FeedConfigError(msg)
    if not all(isinstance(key, str) for key in value):
        msg = f"{label} keys must be strings"
        raise FeedConfigError(msg)
    return value


def _require_non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"{label} must be a non-empty string"
        raise FeedConfigError(msg)
    return value.strip()


def _require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        msg = f"{label} must be a non-empty list"
        raise FeedConfigError(msg)
    return [_require_non_empty_string(item, label) for item in value]


def _validate_max_articles_per_topic(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = "settings.max_articles_per_topic must be an integer"
        raise FeedConfigError(msg)
    if not 1 <= value <= _MAX_ARTICLES_PER_TOPIC_LIMIT:
        msg = (
            f"settings.max_articles_per_topic must be between 1 and {_MAX_ARTICLES_PER_TOPIC_LIMIT}"
        )
        raise FeedConfigError(msg)
    return value
