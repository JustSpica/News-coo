from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import discord
import pytest

from bot.ui.pagination import PaginationView


def _make_pages(count: int = 3) -> list[discord.Embed]:
    return [
        discord.Embed(title=f"Page {i + 1}", description=f"Content {i + 1}") for i in range(count)
    ]


def _make_interaction() -> AsyncMock:
    interaction = AsyncMock()
    interaction.response = AsyncMock()
    return interaction


def _click_button(view: PaginationView, button_label: str) -> None:
    interaction = _make_interaction()
    for child in view.children:
        if isinstance(child, discord.ui.Button) and child.label == button_label:
            asyncio.run(child.callback(interaction))
            return
    msg = f"Button '{button_label}' not found"
    raise ValueError(msg)


class TestPaginationView:
    def test_empty_pages_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one page"):
            PaginationView([])

    def test_current_page_starts_at_first_embed(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages)

        assert view.current_page.title == "Page 1"

    def test_previous_button_starts_disabled(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages)

        assert view.previous_button.disabled is True
        assert view.next_button.disabled is False

    def test_next_button_disabled_on_last_page(self) -> None:
        pages = _make_pages(count=1)
        view = PaginationView(pages)

        assert view.next_button.disabled is True

    def test_next_button_advances_to_next_page(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages)

        _click_button(view, "Next ▶")

        assert view.current_page.title == "Page 2"
        assert view.previous_button.disabled is False

    def test_previous_button_returns_to_prior_page(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages)

        _click_button(view, "Next ▶")
        _click_button(view, "◀ Previous")

        assert view.current_page.title == "Page 1"
        assert view.previous_button.disabled is True

    def test_next_button_does_not_exceed_last_page(self) -> None:
        pages = _make_pages(count=2)
        view = PaginationView(pages)

        _click_button(view, "Next ▶")
        _click_button(view, "Next ▶")

        assert view.current_page.title == "Page 2"
        assert view.next_button.disabled is True

    def test_on_timeout_disables_all_buttons(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages)

        asyncio.run(view.on_timeout())

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True

    def test_custom_timeout_is_applied(self) -> None:
        pages = _make_pages()
        view = PaginationView(pages, timeout=60)

        assert view.timeout == 60
