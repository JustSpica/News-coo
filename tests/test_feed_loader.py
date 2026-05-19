from __future__ import annotations

from core.feed_loader import load_feeds_config


class TestFeedLoaderYaml:
    def test_yaml_with_settings_and_topic_returns_correct_config(self, tmp_path) -> None:
        yaml_content = """\
settings:
  max_articles_per_topic: 5
  min_articles_per_source: 2

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
        assert settings.min_articles_per_source == 2
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
        assert settings.min_articles_per_source == 1
        assert topics == []
