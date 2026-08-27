"""Sistema minimo especifico deste jogo: sai ao apertar a acao 'quit' (ESC)."""
from __future__ import annotations

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class QuitOnActionSystem(ISystem):
    """
    Chama `game_loop.stop()` quando a acao `quit` (ligada a ESC em
    `data/input_bindings/rhythm_keyboard.json`) e pressionada.

    `GameLoop.run()` so encerra nativamente por `wants_quit()` (fechar a
    janela) -- este system e o jeito mais simples de dar uma saida pelo
    teclado sem construir um sistema de pause/menu completo (fora de
    escopo deste vertical slice). `game_loop` e injetado no construtor
    porque `ISystem.update(world, delta_time)` nao recebe uma referencia
    a ele.
    """

    def __init__(self, input_provider: IInputProvider, game_loop: GameLoop) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed("quit"):
            self._game_loop.stop()
