# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tela de pausa real do Jogo Musical: congela o World e pausa o audio de verdade."""
from __future__ import annotations

from typing import Tuple

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.world import World
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

_OVERLAY_RGBA = (0, 0, 0, 160)
_TEXT_WHITE = (255, 255, 255, 255)


class PauseScene(IScene):
    """
    Cena de pausa: `update()` nao faz NADA a nao ser checar a acao de
    despausar (o `World` fica genuinamente congelado -- nenhum `ISystem`
    roda enquanto esta cena estiver no topo, incluindo
    `RhythmSpawnerSystem`/`JudgmentSystem`, que so veem `world.step()`
    de novo depois do pop). `render()` redesenha o ultimo frame de
    gameplay congelado (via a MESMA instancia de `GameplayScene` que ja
    e a base da pilha -- stateless, reutilizavel, sem duplicar a logica
    de gather+draw) e por cima um overlay translucido + "PAUSADO".

    `on_enter`/`on_exit` pausam/retomam o audio de verdade
    (`IAudioEngine.pause_track`/`resume_track`) -- sem isso, o
    `IAudioClock` continuaria avancando contra o tempo real de parede
    enquanto o `World` fica parado, e ao despausar toda nota "em voo"
    seria auto-errada de uma vez (achado da revisao do plano).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        game_loop: GameLoop,
        audio_engine: IAudioEngine,
        track_id: str,
        gameplay_scene: GameplayScene,
        viewport_size: Tuple[int, int],
        pause_action_name: str = "pause",
    ) -> None:
        self._input_provider = input_provider
        self._game_loop = game_loop
        self._audio_engine = audio_engine
        self._track_id = track_id
        self._gameplay_scene = gameplay_scene
        self._viewport_width, self._viewport_height = viewport_size
        self._pause_action_name = pause_action_name

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        self._audio_engine.pause_track(self._track_id)

    def on_exit(self, world: World, renderer: IRenderer) -> None:
        self._audio_engine.resume_track(self._track_id)

    def update(self, world: World, delta_time: float) -> None:
        if self._input_provider.is_action_pressed(self._pause_action_name):
            self._game_loop.pop_scene()

    def render(self, world: World, renderer: IRenderer) -> None:
        self._gameplay_scene.render(world, renderer)
        renderer.draw_ui_rect(0, 0, self._viewport_width, self._viewport_height, _OVERLAY_RGBA)
        renderer.draw_text(
            self._viewport_width / 2.0,
            self._viewport_height / 2.0,
            "PAUSADO",
            32,
            _TEXT_WHITE,
            anchor="center",
        )
        renderer.draw_text(
            self._viewport_width / 2.0,
            self._viewport_height / 2.0 + 36.0,
            "P para continuar",
            16,
            _TEXT_WHITE,
            anchor="center",
        )
