# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sistema minimo especifico deste jogo: sai ao apertar a acao 'quit' (ESC)."""
from __future__ import annotations

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class QuitOnActionSystem(ISystem):
    """Chama `game_loop.stop()` quando a acao `quit` (ligada a ESC em
    `data/input_bindings/platformer_keyboard.json`) e pressionada -- sem
    menu neste v1 (ver ROADMAP M12), 'quit' encerra o processo direto."""

    def __init__(self, input_provider: IInputProvider, game_loop: GameLoop) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed("quit"):
            self._game_loop.stop()
