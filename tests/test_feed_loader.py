from __future__ import annotations

import pytest

from core.feed_loader import FeedConfigError, load_feeds_config


class TestFeedLoaderYaml:
    def test_yaml_with_settings_and_topic_returns_correct_config(self, tmp_path) -> None:
        yaml_content = """\
settings:
  max_articles_per_topic: 5

topics:
  economia:
    display_name: "Economia"
    keywords:
      - "economia"
      - "mercado"
    language: pt
    sources:
      - name: Reuters
        domain: reuters.com
"""
        yaml_file = tmp_path / "feeds.yaml"
        yaml_file.write_text(yaml_content)

        settings, topics = load_feeds_config(yaml_file)

        assert settings.max_articles_per_topic == 5
        assert len(topics) == 1
        assert topics[0].key == "economia"
        assert topics[0].display_name == "Economia"
        assert topics[0].keywords == ["economia", "mercado"]
        assert topics[0].language == "pt"
        assert len(topics[0].sources) == 1

        source = topics[0].sources[0]
        assert source.name == "Reuters"
        assert source.domain == "reuters.com"

    def test_yaml_without_settings_returns_defaults(self, tmp_path) -> None:
        yaml_content = "topics: {}\n"
        yaml_file = tmp_path / "feeds.yaml"
        yaml_file.write_text(yaml_content)

        settings, topics = load_feeds_config(yaml_file)

        assert settings.max_articles_per_topic == 15
        assert topics == []

    @pytest.mark.parametrize(
        ("yaml_content", "message"),
        [
            ("", "feeds config must be a mapping"),
            (
                """\
settings:
  unknown_setting: true
topics: {}
""",
                "Unknown feed setting",
            ),
            (
                """\
settings:
  max_articles_per_topic: 0
topics: {}
""",
                "max_articles_per_topic must be between",
            ),
            (
                """\
topics:
  test:
    display_name: Test
    keywords:
      - news
    language: fr
    sources:
      - name: Example
        domain: example.com
""",
                "Unsupported language",
            ),
            (
                """\
topics:
  test:
    display_name: Test
    keywords: []
    language: en
    sources:
      - name: Example
        domain: example.com
""",
                "keywords must be a non-empty list",
            ),
            (
                """\
topics:
  test:
    display_name: Test
    keywords:
      - news
    language: en
    sources:
      - name: Example
        domain: "example.com&bad=true"
""",
                "domain is invalid",
            ),
        ],
    )
    def test_invalid_yaml_raises_config_error(
        self,
        tmp_path,
        yaml_content: str,
        message: str,
    ) -> None:
        yaml_file = tmp_path / "feeds.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(FeedConfigError, match=message):
            load_feeds_config(yaml_file)
