from __future__ import annotations

import importlib

import pytest

from config.settings import get_discord_token


class TestSettings:
    def test_digest_import_does_not_require_discord_token(self, monkeypatch) -> None:
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)

        importlib.import_module("bot.cogs.digest")

    def test_get_discord_token_returns_environment_value(self, monkeypatch) -> None:
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")

        assert get_discord_token() == "test-token"

    def test_get_discord_token_raises_clear_error_when_missing(self, monkeypatch) -> None:
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)

        with pytest.raises(RuntimeError, match="DISCORD_TOKEN must be set"):
            get_discord_token()
