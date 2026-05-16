from __future__ import annotations

import discord

DEFAULT_PAGINATION_TIMEOUT_SECONDS = 300


class PaginationView(discord.ui.View):
    """Paginated embed navigation with Previous/Next buttons.

    Usage:
        pages = [embed_1, embed_2, embed_3]
        view = PaginationView(pages)
        await interaction.followup.send(embed=view.current_page, view=view)
    """

    def __init__(
        self,
        pages: list[discord.Embed],
        *,
        timeout: float = DEFAULT_PAGINATION_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(timeout=timeout)
        self._pages = pages
        self._current_index = 0
        self._update_button_states()

    @property
    def current_page(self) -> discord.Embed:
        return self._pages[self._current_index]

    def _update_button_states(self) -> None:
        self.previous_button.disabled = self._current_index == 0
        self.next_button.disabled = self._current_index >= len(self._pages) - 1

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self._current_index = max(0, self._current_index - 1)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.current_page, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self._current_index = min(len(self._pages) - 1, self._current_index + 1)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.current_page, view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
