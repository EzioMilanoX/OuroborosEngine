# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sistema minimo especifico deste jogo: empilha a PauseScene ao apertar a acao 'pause'."""
from __future__ import annotations

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import IScene
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class PauseOnActionSystem(ISystem):
    """
    Chama `game_loop.push_scene(pause_scene)` quando a acao `pause`
    (ligada a P em `data/input_bindings/rhythm_keyboard.json`) e
    pressionada. Mesmo molde de `QuitOnActionSystem`: `game_loop` e
    injetado no construtor porque `ISystem.update(world, delta_time)`
    nao recebe uma referencia a ele.

    So e alcancado enquanto `GameplayScene` estiver no topo da pilha
    (e o que de fato chama `world.step()`, que roda este `ISystem`) --
    isso ja impede sozinho um re-disparo enquanto `PauseScene` estiver
    ativa, sem precisar de nenhuma guarda extra aqui. `PauseScene.update()`
    e quem checa a MESMA acao pra desempilhar (ver `pause_scene.py`).
    """

    def __init__(self, input_provider: IInputProvider, game_loop: GameLoop, pause_scene: IScene) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop
        self._pause_scene = pause_scene

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed("pause"):
            self._game_loop.push_scene(self._pause_scene)
