# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tela de fim de jogo (derrota/vitoria): congela o jogo e permite sair, sem depender de ISystem."""
from __future__ import annotations

from typing import Tuple

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

_OVERLAY_RGBA = (0, 0, 0, 180)
_TEXT_WHITE = (255, 255, 255, 255)


class EndScene(IScene):
    """
    Cena de fim de jogo -- NUNCA da pop em si mesma (fim de jogo e
    definitivo; unico lugar onde a pilha de cenas aceita uma cena "sem
    volta", o que `IScene`/`GameLoop` ja suportam sem nenhuma suposicao
    contraria).

    `update()` checa a acao `quit` DIRETO (nao depende de
    `QuitOnActionSystem`, que fica congelado assim que esta cena e
    empilhada -- `world.step()` so roda enquanto `GameplayScene` esta
    no topo da pilha) -- mesmo idioma auto-suficiente ja usado por
    `PauseScene` (Jogo Musical) pra despausar.

    `render()` redesenha o ultimo frame de gameplay congelado via a
    MESMA instancia de `GameplayScene` que ja e a base da pilha
    (stateless, reutilizavel, sem duplicar logica de gather+draw --
    mesmo idioma de `PauseScene`), com um overlay + mensagem por cima.
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        game_loop: GameLoop,
        gameplay_scene: GameplayScene,
        message: str,
        viewport_size: Tuple[int, int],
        quit_action_name: str = "quit",
    ) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop
        self._gameplay_scene = gameplay_scene
        self._message = message
        self._viewport_width, self._viewport_height = viewport_size
        self._quit_action_name = quit_action_name

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed(self._quit_action_name):
            self._game_loop.stop()

    def render(self, world: World, renderer: IRenderer) -> None:
        self._gameplay_scene.render(world, renderer)
        renderer.draw_ui_rect(0, 0, self._viewport_width, self._viewport_height, _OVERLAY_RGBA)
        renderer.draw_text(
            self._viewport_width / 2.0,
            self._viewport_height / 2.0,
            self._message,
            32,
            _TEXT_WHITE,
            anchor="center",
        )
        renderer.draw_text(
            self._viewport_width / 2.0,
            self._viewport_height / 2.0 + 36.0,
            "ESC para sair",
            16,
            _TEXT_WHITE,
            anchor="center",
        )
