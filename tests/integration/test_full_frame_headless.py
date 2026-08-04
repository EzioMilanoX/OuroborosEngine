# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Integracao ponta-a-ponta do laco de frame (GameLoop -> World.step ->
IRenderer) usando exclusivamente os backends Null (Pilar 2), sem
inicializar video/audio reais -- exercita a composicao completa dos
Pilares 1, 2 e do bootstrap sem depender de pygame de verdade.
"""
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.physics_system import PhysicsSystem
from ouroboros.interfaces.null.null_input_provider import NullInputProvider


class QuitAfterNPolls(NullInputProvider):
    """Duble de teste: sinaliza `wants_quit()` apos N chamadas de `poll()`, para tornar `GameLoop.run()` deterministico."""

    def __init__(self, quit_after: int) -> None:
        super().__init__()
        self._polls = 0
        self._quit_after = quit_after

    def poll(self) -> None:
        super().poll()
        self._polls += 1

    def wants_quit(self) -> bool:
        return self._polls >= self._quit_after


def test_game_loop_runs_fixed_number_of_frames_and_renders_sprites(memory_manager, world, null_renderer, null_audio_engine):
    world.register_archetype("sprite_entity", ("transform", "sprite"))
    world.register_system(PhysicsSystem(memory_manager))

    handle = world.create_entity("sprite_entity")
    index = unpack_index(handle)
    transform_pool = world.get_pool("transform")
    velocity_pool = world.get_pool("velocity")
    sprite_pool = world.get_pool("sprite")

    velocity_pool.attach(index)
    t_row = transform_pool.dense_row_of(index)
    transform_pool.active_view()["position_x"][t_row] = 0.0
    v_row = velocity_pool.dense_row_of(index)
    velocity_pool.active_view()["linear_x"][v_row] = 1.0
    s_row = sprite_pool.dense_row_of(index)
    sprite_pool.active_view()["texture_id"][s_row] = 7

    quitter = QuitAfterNPolls(quit_after=3)
    game_loop = GameLoop(world, null_renderer, quitter, null_audio_engine, target_fps=0)

    game_loop.run()

    assert null_renderer.begin_frame_count == 3
    assert null_renderer.end_frame_count == 3
    assert null_renderer.draw_batch_calls == [1, 1, 1]

    # PhysicsSystem ran every frame -- position must have moved (dt > 0 each frame).
    final_row = transform_pool.dense_row_of(index)
    assert transform_pool.active_view()["position_x"][final_row] > 0.0


def test_game_loop_renders_zero_sprites_when_no_entity_has_both_transform_and_sprite(world, null_renderer, null_audio_engine):
    quitter = QuitAfterNPolls(quit_after=1)
    game_loop = GameLoop(world, null_renderer, quitter, null_audio_engine, target_fps=0)

    game_loop.run()

    assert null_renderer.draw_batch_calls == [0]


def test_game_loop_stop_halts_the_loop_from_within_a_system(world, null_renderer, null_audio_engine):
    call_count = {"n": 0}

    class StoppingSystem:
        def update(self, inner_world, delta_time):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                game_loop.stop()

    world.register_system(StoppingSystem())
    input_provider = NullInputProvider()  # never signals wants_quit on its own
    game_loop = GameLoop(world, null_renderer, input_provider, null_audio_engine, target_fps=0)

    game_loop.run()

    assert call_count["n"] == 2
    assert null_renderer.begin_frame_count == 2
