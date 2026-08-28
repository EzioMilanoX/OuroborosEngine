# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa a pilha de cenas do GameLoop (ROADMAP M2): push/pop, on_enter/on_exit, e que
so o topo da pilha recebe update()/render() a cada frame."""
from __future__ import annotations

import pytest

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.interfaces.null.null_input_provider import NullInputProvider


class RecordingScene(IScene):
    """Cena de teste: registra cada chamada de update/render/on_enter/on_exit, na ordem."""

    def __init__(self, name: str, calls: list) -> None:
        self._name = name
        self._calls = calls

    def on_enter(self, world, renderer) -> None:
        self._calls.append(("on_enter", self._name))

    def on_exit(self, world, renderer) -> None:
        self._calls.append(("on_exit", self._name))

    def update(self, world, delta_time) -> None:
        self._calls.append(("update", self._name))

    def render(self, world, renderer) -> None:
        self._calls.append(("render", self._name))


@pytest.fixture
def game_loop(world, null_renderer, null_audio_engine) -> GameLoop:
    return GameLoop(world, null_renderer, NullInputProvider(), null_audio_engine, target_fps=0)


def test_stack_starts_with_a_single_gameplay_scene(game_loop: GameLoop):
    assert isinstance(game_loop.current_scene, GameplayScene)


def test_push_scene_calls_on_exit_of_previous_top_and_on_enter_of_new_top(game_loop: GameLoop):
    calls = []
    base = game_loop.current_scene
    scene_a = RecordingScene("a", calls)

    game_loop.push_scene(scene_a)

    assert game_loop.current_scene is scene_a
    assert calls == [("on_enter", "a")]  # base GameplayScene nao registra chamadas (nao e RecordingScene)


def test_pop_scene_calls_on_exit_of_popped_and_on_enter_of_revealed(game_loop: GameLoop):
    calls = []
    scene_a = RecordingScene("a", calls)
    game_loop.push_scene(scene_a)
    calls.clear()

    popped = game_loop.pop_scene()

    assert popped is scene_a
    assert calls == [("on_exit", "a")]
    assert isinstance(game_loop.current_scene, GameplayScene)


def test_push_scene_calls_on_exit_of_a_recording_base_scene_too(game_loop: GameLoop, monkeypatch):
    calls = []
    # substitui a base por uma RecordingScene pra observar seu on_exit tambem
    recording_base = RecordingScene("base", calls)
    game_loop._scenes[0] = recording_base
    scene_a = RecordingScene("a", calls)

    game_loop.push_scene(scene_a)

    assert calls == [("on_exit", "base"), ("on_enter", "a")]


def test_pop_scene_on_the_last_remaining_scene_raises(game_loop: GameLoop):
    with pytest.raises(RuntimeError):
        game_loop.pop_scene()


def test_multiple_pushes_and_pops_form_a_correct_stack(game_loop: GameLoop):
    calls = []
    scene_a = RecordingScene("a", calls)
    scene_b = RecordingScene("b", calls)

    game_loop.push_scene(scene_a)
    game_loop.push_scene(scene_b)
    assert game_loop.current_scene is scene_b

    game_loop.pop_scene()
    assert game_loop.current_scene is scene_a

    game_loop.pop_scene()
    assert isinstance(game_loop.current_scene, GameplayScene)


def test_run_calls_update_and_render_only_on_the_top_scene(game_loop: GameLoop, bind_quit_after):
    calls = []
    scene_a = RecordingScene("a", calls)
    game_loop.push_scene(scene_a)
    calls.clear()  # descarta o on_enter do push acima

    bind_quit_after(game_loop.input_provider, quit_after=3)
    game_loop.run()

    # 3 frames -> exatamente 3 updates e 3 renders da cena "a", nada da GameplayScene por baixo
    assert calls == [("update", "a"), ("render", "a")] * 3


def test_game_loop_behavior_is_unchanged_when_no_scene_is_ever_pushed(
    memory_manager, world, null_renderer, null_audio_engine, bind_quit_after
):
    """Regressao de retrocompatibilidade: sem nenhum push_scene, o comportamento e
    identico ao GameLoop de antes do SceneStack existir (ver tests/integration/
    test_full_frame_headless.py, que exercita isso sem nenhuma mudanca de asssercao)."""
    from ouroboros.core.systems.physics_system import PhysicsSystem
    from ouroboros.core.memory.handles import unpack_index

    world.register_archetype("mover", ("transform", "sprite", "velocity"))
    world.register_system(PhysicsSystem(memory_manager))
    handle = world.create_entity("mover")
    index = unpack_index(handle)
    world.get_pool("velocity").active_view()["linear_x"][world.get_pool("velocity").dense_row_of(index)] = 1.0

    game_loop = GameLoop(world, null_renderer, NullInputProvider(), null_audio_engine, target_fps=0)
    bind_quit_after(game_loop.input_provider, quit_after=2)

    game_loop.run()

    assert null_renderer.begin_frame_count == 2
    assert null_renderer.end_frame_count == 2
    assert null_renderer.draw_batch_calls == [1, 1]
