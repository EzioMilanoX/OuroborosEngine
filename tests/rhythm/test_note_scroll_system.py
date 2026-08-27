# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
NoteScrollSystem deve posicionar notas como funcao PURA do tempo real
restante (via IAudioClock), nunca integrando delta_time -- a posicao de
uma nota deve ser exatamente a mesma independente de quantos frames (ou
de que tamanho de delta_time) se passaram, desde que now_seconds() seja
o mesmo.
"""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.handles import unpack_index
from ouroboros.rhythm.runtime.note_scroll_system import NoteScrollSystem
from ouroboros.rhythm.runtime.schemas import NOTE_STATE_DTYPE

LANE_POOL_NAME = "lane"
NOTE_STATE_POOL_NAME = "note_state"
ARCHETYPE_NAME = "note"

JUDGMENT_LINE_Y = 500.0
SCROLL_SPEED = 300.0
LANE_X_POSITIONS = (100.0, 200.0, 300.0, 400.0)


def _register_note_archetype(memory_manager, world):
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, ("transform", LANE_POOL_NAME, NOTE_STATE_POOL_NAME))


def _spawn_note(world, lane: int, timestamp_seconds: float):
    packed = world.create_entity(ARCHETYPE_NAME)
    index = unpack_index(packed)
    world.get_pool(LANE_POOL_NAME).active_view()["lane"][world.get_pool(LANE_POOL_NAME).dense_row_of(index)] = lane
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    row = note_state_pool.dense_row_of(index)
    note_state_pool.active_view()["timestamp_seconds"][row] = timestamp_seconds
    note_state_pool.active_view()["packed_entity_id"][row] = packed
    return packed


def _make_system(audio_clock) -> NoteScrollSystem:
    return NoteScrollSystem(
        audio_clock=audio_clock,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        transform_pool_name="transform",
        lane_pool_name=LANE_POOL_NAME,
        lane_x_positions=LANE_X_POSITIONS,
        judgment_line_y=JUDGMENT_LINE_Y,
        scroll_speed_px_per_sec=SCROLL_SPEED,
    )


def test_note_exactly_at_judgment_line_when_time_until_hit_is_zero(memory_manager, world, null_audio_clock):
    _register_note_archetype(memory_manager, world)
    packed = _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock)

    null_audio_clock.set_now_seconds(1.0)
    system.update(world, delta_time=0.016)

    transform_pool = world.get_pool("transform")
    row = transform_pool.dense_row_of(unpack_index(packed))
    assert transform_pool.active_view()["position_y"][row] == JUDGMENT_LINE_Y
    assert transform_pool.active_view()["position_x"][row] == LANE_X_POSITIONS[0]


def test_note_above_line_before_hit_time_and_below_after(memory_manager, world, null_audio_clock):
    _register_note_archetype(memory_manager, world)
    packed = _spawn_note(world, lane=2, timestamp_seconds=2.0)
    system = _make_system(null_audio_clock)
    transform_pool = world.get_pool("transform")
    row = transform_pool.dense_row_of(unpack_index(packed))

    null_audio_clock.set_now_seconds(1.0)  # 1s antes do hit -> ainda por vir
    system.update(world, delta_time=0.016)
    y_before = transform_pool.active_view()["position_y"][row]
    assert y_before < JUDGMENT_LINE_Y  # y cresce para baixo: "antes" fica ACIMA da linha

    null_audio_clock.set_now_seconds(3.0)  # 1s depois do hit -> ja vencida
    system.update(world, delta_time=0.016)
    y_after = transform_pool.active_view()["position_y"][row]
    assert y_after > JUDGMENT_LINE_Y  # "depois" continua descendo, abaixo da linha

    assert transform_pool.active_view()["position_x"][row] == LANE_X_POSITIONS[2]


def test_position_is_pure_function_of_clock_not_of_delta_time(memory_manager, world, null_audio_clock):
    """Mesmo now_seconds(), delta_time completamente diferente -> posicao IDENTICA."""
    _register_note_archetype(memory_manager, world)
    packed = _spawn_note(world, lane=1, timestamp_seconds=5.0)
    system = _make_system(null_audio_clock)
    transform_pool = world.get_pool("transform")
    row = transform_pool.dense_row_of(unpack_index(packed))

    null_audio_clock.set_now_seconds(4.0)
    system.update(world, delta_time=0.001)
    y_tiny_dt = transform_pool.active_view()["position_y"][row]

    system.update(world, delta_time=999.0)  # mesmo now_seconds(), delta_time gigante
    y_huge_dt = transform_pool.active_view()["position_y"][row]

    assert y_tiny_dt == y_huge_dt


def test_multiple_notes_in_different_lanes_positioned_independently(memory_manager, world, null_audio_clock):
    _register_note_archetype(memory_manager, world)
    packed_a = _spawn_note(world, lane=0, timestamp_seconds=1.0)
    packed_b = _spawn_note(world, lane=3, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock)

    null_audio_clock.set_now_seconds(1.0)
    system.update(world, delta_time=0.016)

    transform_pool = world.get_pool("transform")
    row_a = transform_pool.dense_row_of(unpack_index(packed_a))
    row_b = transform_pool.dense_row_of(unpack_index(packed_b))
    assert transform_pool.active_view()["position_x"][row_a] == LANE_X_POSITIONS[0]
    assert transform_pool.active_view()["position_x"][row_b] == LANE_X_POSITIONS[3]
    # mesmo timestamp/now -> mesma position_y, mesmo estando em lanes diferentes
    assert transform_pool.active_view()["position_y"][row_a] == transform_pool.active_view()["position_y"][row_b]


def test_no_active_notes_does_not_raise(memory_manager, world, null_audio_clock):
    _register_note_archetype(memory_manager, world)
    system = _make_system(null_audio_clock)
    null_audio_clock.set_now_seconds(5.0)
    system.update(world, delta_time=0.016)  # nao deve levantar erro sem nenhuma nota ativa
