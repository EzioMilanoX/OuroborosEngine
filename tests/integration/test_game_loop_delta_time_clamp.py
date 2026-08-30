# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa que GameLoop.run() nunca repassa um delta_time maior que MAX_DELTA_TIME_SECONDS
(ROADMAP M12 -- achado da critica: sem isso, um pico real de tempo entre dois frames
-- janela arrastada, pausa de GC -- atravessaria qualquer entidade por geometria solida
num unico passo de integracao, algo que TileCollisionSystem nao tem como detectar)."""
from __future__ import annotations

import ouroboros.bootstrap.game_loop as game_loop_module
from ouroboros.bootstrap.game_loop import MAX_DELTA_TIME_SECONDS, GameLoop
from ouroboros.bootstrap.scene import IScene
from ouroboros.interfaces.null.null_input_provider import NullInputProvider


class _RecordingDeltaTimeScene(IScene):
    def __init__(self) -> None:
        self.delta_times = []

    def update(self, world, delta_time: float) -> None:
        self.delta_times.append(delta_time)

    def render(self, world, renderer) -> None:
        pass


def test_run_clamps_a_huge_delta_time_spike(world, null_renderer, null_audio_engine, monkeypatch):
    scene = _RecordingDeltaTimeScene()
    input_provider = NullInputProvider()
    loop = GameLoop(world, null_renderer, input_provider, null_audio_engine, target_fps=0)
    loop.reset_scenes(scene)

    # 2 iteracoes: a 1a com delta_time normal (0.0), a 2a com um pico gigante (50s) --
    # cada iteracao consulta perf_counter() 2x (now + elapsed), mais 1x antes do loop.
    perf_counter_values = iter([0.0, 0.0, 0.0, 50.0, 50.0])
    monkeypatch.setattr(game_loop_module.time, "perf_counter", lambda: next(perf_counter_values))

    poll_count = {"n": 0}
    original_poll = input_provider.poll

    def counting_poll() -> None:
        original_poll()
        poll_count["n"] += 1

    input_provider.poll = counting_poll
    input_provider.wants_quit = lambda: poll_count["n"] >= 2

    loop.run()

    assert scene.delta_times == [0.0, MAX_DELTA_TIME_SECONDS]


def test_run_does_not_clamp_a_normal_delta_time(world, null_renderer, null_audio_engine, monkeypatch):
    scene = _RecordingDeltaTimeScene()
    input_provider = NullInputProvider()
    loop = GameLoop(world, null_renderer, input_provider, null_audio_engine, target_fps=0)
    loop.reset_scenes(scene)

    perf_counter_values = iter([0.0, 0.016, 0.016])
    monkeypatch.setattr(game_loop_module.time, "perf_counter", lambda: next(perf_counter_values))
    input_provider.wants_quit = lambda: len(scene.delta_times) >= 1

    loop.run()

    assert scene.delta_times == [0.016]
