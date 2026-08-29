"""Sistema minimo especifico deste jogo: reage a acao 'quit' (ESC) via um callback injetado."""
from __future__ import annotations

from typing import Callable

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider


class QuitOnActionSystem(ISystem):
    """
    Chama `on_quit_action()` quando a acao `quit` (ligada a ESC em
    `data/input_bindings/rhythm_keyboard.json`) e pressionada.

    `GameLoop.run()` so encerra nativamente por `wants_quit()` (fechar a
    janela) -- este system e o jeito mais simples de dar uma saida pelo
    teclado sem depender de nenhum `ISystem` de outra cena (que fica
    congelado assim que outra cena toma o topo da pilha).

    `on_quit_action` (nao mais um `game_loop` direto -- ROADMAP M11.1):
    o que "sair" significa depende de ONDE este sistema esta registrado --
    durante uma musica em andamento, "sair" volta pro `MenuScene` (nao
    encerra o processo); so o proprio `MenuScene.update()` (que roda sem
    nenhum `World`/`ISystem` por baixo -- ver seu docstring) chama
    `game_loop.stop()` de verdade. O chamador decide, injetando o callback
    certo; este sistema nao sabe a diferenca.
    """

    def __init__(self, input_provider: IInputProvider, on_quit_action: Callable[[], None]) -> None:
        self._input_provider = input_provider
        self._on_quit_action = on_quit_action

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input_provider.is_action_pressed("quit"):
            self._on_quit_action()
