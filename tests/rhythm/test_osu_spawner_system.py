# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de OsuSpawnerSystem (ROADMAP M15): mesma disciplina de test_rhythm_spawner_uses_audio_clock_not_dt.py."""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, unpack_index
from ouroboros.rhythm.runtime.osu_spawner_system import OsuSpawnerSystem
from ouroboros.rhythm.runtime.schemas import OSU_NOTE_STATE_DTYPE, OSU_SCHEDULED_HIT_DTYPE, OsuObjectKind

NOTE_STATE_POOL_NAME = "osu_note_state"
ARCHETYPE_NAME = "osu_note"


def _build_scheduled_hits() -> np.ndarray:
    scheduled = np.zeros(3, dtype=OSU_SCHEDULED_HIT_DTYPE)
    scheduled["timestamp_seconds"] = [1.0, 2.0, 3.0]
    scheduled["threat_type"] = [OsuObjectKind.CIRCLE, OsuObjectKind.SLIDER, OsuObjectKind.CIRCLE]
    scheduled["x"] = [10.0, 20.0, 30.0]
    scheduled["y"] = [15.0, 25.0, 35.0]
    scheduled["end_x"] = [0.0, 60.0, 0.0]
    scheduled["end_y"] = [0.0, 70.0, 0.0]
    scheduled["duration_seconds"] = [0.0, 0.5, 0.0]
    scheduled["strength"] = [0.1, 0.2, 0.3]
    scheduled["layer"] = [0, 1, 0]
    return scheduled


def _register_osu_note_archetype(memory_manager, world) -> None:
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, OSU_NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, (NOTE_STATE_POOL_NAME,))


def test_full_lifecycle_uses_audio_clock_not_delta_time(memory_manager, world, null_audio_clock):
    _register_osu_note_archetype(memory_manager, world)
    system = OsuSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_hits=_build_scheduled_hits(),
        hit_archetype_name=ARCHETYPE_NAME,
        osu_note_state_pool_name=NOTE_STATE_POOL_NAME,
    )
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)

    system.update(world, delta_time=999.0)
    assert system.next_pending_index == 0
    assert note_state_pool.count == 0

    null_audio_clock.advance(1.2)
    system.update(world, delta_time=0.016)
    assert system.next_pending_index == 1
    assert note_state_pool.count == 1

    system.update(world, delta_time=0.016)  # sem avancar o clock -- idempotente
    assert system.next_pending_index == 1
    assert note_state_pool.count == 1


def test_note_state_fields_are_written_correctly_for_circle_and_slider(memory_manager, world, null_audio_clock):
    _register_osu_note_archetype(memory_manager, world)
    system = OsuSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_hits=_build_scheduled_hits(),
        hit_archetype_name=ARCHETYPE_NAME,
        osu_note_state_pool_name=NOTE_STATE_POOL_NAME,
    )

    null_audio_clock.set_now_seconds(2.5)  # dispara os 2 primeiros (circulo em 1.0, slider em 2.0)
    system.update(world, delta_time=0.016)

    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    view = note_state_pool.active_view()
    assert note_state_pool.count == 2

    circle_row = view[0]
    assert float(circle_row["timestamp_seconds"]) == 1.0
    assert int(circle_row["object_kind"]) == OsuObjectKind.CIRCLE
    assert float(circle_row["x"]) == 10.0
    assert float(circle_row["y"]) == 15.0
    assert float(circle_row["duration_seconds"]) == 0.0
    assert bool(circle_row["is_tracking"]) is False
    assert int(circle_row["ring_entity_id"]) == NULL_PACKED_HANDLE
    assert int(circle_row["ball_entity_id"]) == NULL_PACKED_HANDLE

    slider_row = view[1]
    assert int(slider_row["object_kind"]) == OsuObjectKind.SLIDER
    assert float(slider_row["end_x"]) == 60.0
    assert float(slider_row["end_y"]) == 70.0
    assert float(slider_row["duration_seconds"]) == 0.5


def test_on_hit_object_spawned_callback_receives_all_fields(memory_manager, world, null_audio_clock):
    _register_osu_note_archetype(memory_manager, world)
    calls = []

    def on_hit_object_spawned(callback_world, packed_entity_id, object_kind, x, y, end_x, end_y, duration_seconds, layer):
        calls.append((packed_entity_id, object_kind, x, y, end_x, end_y, duration_seconds, layer))
        assert callback_world is world

    system = OsuSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_hits=_build_scheduled_hits(),
        hit_archetype_name=ARCHETYPE_NAME,
        osu_note_state_pool_name=NOTE_STATE_POOL_NAME,
        on_hit_object_spawned=on_hit_object_spawned,
    )

    null_audio_clock.advance(1.2)
    system.update(world, delta_time=0.016)

    assert len(calls) == 1
    packed_entity_id, object_kind, x, y, end_x, end_y, duration_seconds, layer = calls[0]
    assert world.is_alive(packed_entity_id)
    assert object_kind == OsuObjectKind.CIRCLE
    assert (x, y, end_x, end_y, duration_seconds, layer) == (10.0, 15.0, 0.0, 0.0, 0.0, 0)


def test_hit_times_overrides_timestamp_written_to_note_state(memory_manager, world, null_audio_clock):
    """Mesmo criterio de RhythmSpawnerSystem: com `hit_times`, note_state
    grava o tempo de ACERTO real, nao o timestamp de spawn."""
    _register_osu_note_archetype(memory_manager, world)
    scheduled_hits = _build_scheduled_hits()
    hit_times = np.array([2.5, 3.5, 4.5], dtype=np.float64)
    system = OsuSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_hits=scheduled_hits,
        hit_archetype_name=ARCHETYPE_NAME,
        osu_note_state_pool_name=NOTE_STATE_POOL_NAME,
        hit_times=hit_times,
    )

    null_audio_clock.advance(1.2)
    system.update(world, delta_time=0.016)

    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    assert float(note_state_pool.active_view()[0]["timestamp_seconds"]) == 2.5


def test_is_finished_property_reflects_cursor_position(memory_manager, world, null_audio_clock):
    _register_osu_note_archetype(memory_manager, world)
    system = OsuSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_hits=_build_scheduled_hits(),
        hit_archetype_name=ARCHETYPE_NAME,
        osu_note_state_pool_name=NOTE_STATE_POOL_NAME,
    )
    assert not system.is_finished

    null_audio_clock.set_now_seconds(100.0)
    system.update(world, delta_time=0.016)

    assert system.is_finished
