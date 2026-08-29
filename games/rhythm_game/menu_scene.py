# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tela unica de selecao de musica/dificuldade do Jogo Musical (ROADMAP M11.1)."""
from __future__ import annotations

from typing import Callable, Sequence, Tuple

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer
from ouroboros.rhythm.loaders.song_catalog_loader import SongEntry

_TITLE_COLOR = (255, 255, 255, 255)
_ROW_COLOR = (170, 170, 190, 255)
_CURSOR_ROW_COLOR = (255, 220, 120, 255)
_HINT_COLOR = (150, 150, 170, 255)

MenuRow = Tuple[SongEntry, str]


class MenuScene(IScene):
    """
    Lista, em uma UNICA tela (nao um assistente multi-passo), o produto
    cartesiano `(musica, dificuldade)` dos catalogos reais
    (`SongCatalogLoader`/`RhythmDifficultyLoader`) -- hoje 1 musica x 1
    dificuldade = 1 linha, cresce automaticamente conforme o catalogo
    cresce (ROADMAP M11.2 adiciona uma 2a musica). Navegavel por
    `move_up`/`move_down` (com wraparound) + `confirm`.

    Roda SEM nenhum `World`/`ISystem` por baixo -- o `World` associado ao
    `GameLoop` neste momento e so um placeholder generico que nunca chega
    a dar um `world.step()` (esta cena nunca chama isso). Por isso,
    igual a `PauseScene`/`EndScene`, checa `quit`/`move_up`/`move_down`/
    `confirm` diretamente em `update()`, nao via um `ISystem` registrado
    (que nunca rodaria aqui).

    `quit` AQUI (raiz da pilha de cenas, nada "atras" pra onde uma acao de
    abandonar levaria) encerra o processo de verdade
    (`game_loop.stop()`) -- diferente de `quit` durante uma musica em
    andamento, que volta pra uma nova instancia desta cena (ver
    `QuitOnActionSystem`/`_start_song` em `composition.py`).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        game_loop: GameLoop,
        rows: Sequence[MenuRow],
        on_confirm: Callable[[SongEntry, str], None],
        viewport_size: Tuple[int, int],
        move_action_names: Tuple[str, str] = ("move_up", "move_down"),
        confirm_action_name: str = "confirm",
        quit_action_name: str = "quit",
    ) -> None:
        if not rows:
            raise ValueError("MenuScene precisa de pelo menos 1 linha (musica, dificuldade)")
        self._input_provider = input_provider
        self._game_loop = game_loop
        self._rows = tuple(rows)
        self._on_confirm = on_confirm
        self._viewport_width, self._viewport_height = viewport_size
        self._move_up_action_name, self._move_down_action_name = move_action_names
        self._confirm_action_name = confirm_action_name
        self._quit_action_name = quit_action_name
        self._cursor = 0

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed(self._quit_action_name):
            self._game_loop.stop()
            return
        if self._input_provider.is_action_pressed(self._move_down_action_name):
            self._cursor = (self._cursor + 1) % len(self._rows)
        if self._input_provider.is_action_pressed(self._move_up_action_name):
            self._cursor = (self._cursor - 1) % len(self._rows)
        if self._input_provider.is_action_pressed(self._confirm_action_name):
            self.confirm_selection()

    def confirm_selection(self) -> None:
        """Confirma a linha atualmente sob o cursor -- mesmo caminho de
        codigo que `update()` usa ao ver a acao `confirm` pressionada.
        Publico para permitir iniciar uma musica programaticamente (ex.:
        `composition.build_game`, que inicia a linha 0 direto, sem
        simular nenhuma tecla -- mesmo espirito do atalho `--play` do
        BulletHell, ver ROADMAP M8c)."""
        song, difficulty_id = self._rows[self._cursor]
        self._on_confirm(song, difficulty_id)

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        renderer.draw_text(
            self._viewport_width / 2.0, 60.0, "JOGO MUSICAL", 32, _TITLE_COLOR, anchor="center"
        )
        row_y = 160.0
        row_spacing = 36.0
        for index, (song, difficulty_id) in enumerate(self._rows):
            is_cursor_row = index == self._cursor
            label = f"{'> ' if is_cursor_row else '  '}{song.display_name} -- {difficulty_id}"
            color = _CURSOR_ROW_COLOR if is_cursor_row else _ROW_COLOR
            renderer.draw_text(
                self._viewport_width / 2.0, row_y + index * row_spacing, label, 22, color, anchor="center"
            )
        renderer.draw_text(
            self._viewport_width / 2.0,
            self._viewport_height - 40.0,
            "Setas para navegar, ENTER para confirmar, ESC para sair",
            14,
            _HINT_COLOR,
            anchor="center",
        )
