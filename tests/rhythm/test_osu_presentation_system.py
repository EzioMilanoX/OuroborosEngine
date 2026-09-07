# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testes de OsuPresentationSystem (ROADMAP M15) -- cobre em particular o
mascaramento de `NULL_PACKED_HANDLE` ANTES de resolver `ring_entity_id`/
`ball_entity_id` (achado real e critico da critica de M15): sem isso, um
CIRCLE (cujo `ball_entity_id` e permanentemente o sentinela) faz
`unpack_batch`/`dense_rows_of` estourar `IndexError` no primeiro frame,
ja que `NULL_PACKED_HANDLE` empacota um indice `0xFFFFFFFF` (positivo
enorme, nao -1).
"""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, unpack_index
from ouroboros.rhythm.runtime.osu_presentation_system import OsuPresentationSystem
from ouroboros.rhythm.runtime.schemas import OSU_NOTE_STATE_DTYPE, OsuObjectKind

NOTE_STATE_POOL_NAME = "osu_note_state"
NOTE_ARCHETYPE_NAME = "osu_note"
COMPANION_ARCHETYPE_NAME = "osu_visual_marker"

APPROACH_SECONDS = 1.0
RING_START_SCALE = 3.0
RING_END_SCALE = 1.0


def _register_archetypes(memory_manager, world):
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, OSU_NOTE_STATE_DTYPE)
    world.register_archetype(NOTE_ARCHETYPE_NAME, (NOTE_STATE_POOL_NAME,))
    world.register_archetype(COMPANION_ARCHETYPE_NAME, ("transform",))


def _spawn_note(world, object_kind: int, timestamp_seconds: float, x=0.0, y=0.0, end_x=0.0, end_y=0.0, duration_seconds=0.0):
    packed = world.create_entity(NOTE_ARCHETYPE_NAME)
    index = unpack_index(packed)
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    row = note_state_pool.dense_row_of(index)
    view = note_state_pool.active_view()
    view["timestamp_seconds"][row] = timestamp_seconds
    view["packed_entity_id"][row] = packed
    view["object_kind"][row] = object_kind
    view["x"][row] = x
    view["y"][row] = y
    view["end_x"][row] = end_x
    view["end_y"][row] = end_y
    view["duration_seconds"][row] = duration_seconds
    view["ring_entity_id"][row] = NULL_PACKED_HANDLE
    view["ball_entity_id"][row] = NULL_PACKED_HANDLE
    view["is_tracking"][row] = False
    return packed, row


def _spawn_companion(world, x=0.0, y=0.0):
    packed = world.create_entity(COMPANION_ARCHETYPE_NAME)
    index = unpack_index(packed)
    transform_pool = world.get_pool("transform")
    t_row = transform_pool.dense_row_of(index)
    view = transform_pool.active_view()
    view["position_x"][t_row] = x
    view["position_y"][t_row] = y
    view["scale_x"][t_row] = 1.0
    view["scale_y"][t_row] = 1.0
    return packed


def _make_system(audio_clock) -> OsuPresentationSystem:
    return OsuPresentationSystem(
        audio_clock=audio_clock,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        transform_pool_name="transform",
        approach_seconds=APPROACH_SECONDS,
        ring_start_scale=RING_START_SCALE,
        ring_end_scale=RING_END_SCALE,
    )


def test_circle_with_null_ball_entity_id_never_crashes(memory_manager, world, null_audio_clock):
    """Regressao direta do bug mais critico achado pela critica de M15:
    um CIRCLE tem `ball_entity_id == NULL_PACKED_HANDLE` para sempre --
    resolver a coluna inteira sem mascarar isso primeiro estourava
    IndexError no primeiro frame."""
    _register_archetypes(memory_manager, world)
    _, row = _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=10.0, y=20.0)
    ring_packed = _spawn_companion(world, x=10.0, y=20.0)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()["ring_entity_id"][row] = ring_packed

    system = _make_system(null_audio_clock)
    null_audio_clock.set_now_seconds(0.5)

    system.update(world, delta_time=0.016)  # NAO deve levantar IndexError


def test_ring_scale_shrinks_linearly_toward_hit_time(memory_manager, world, null_audio_clock):
    _register_archetypes(memory_manager, world)
    _, row = _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=10.0, y=20.0)
    ring_packed = _spawn_companion(world)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()["ring_entity_id"][row] = ring_packed
    ring_index = unpack_index(ring_packed)
    transform_pool = world.get_pool("transform")

    system = _make_system(null_audio_clock)

    null_audio_clock.set_now_seconds(0.0)  # 1s antes do hit -- fracao 1.0 (approach_seconds=1.0)
    system.update(world, delta_time=0.016)
    scale_at_spawn = float(transform_pool.active_view()["scale_x"][transform_pool.dense_row_of(ring_index)])
    assert scale_at_spawn == pytest.approx(RING_START_SCALE)

    null_audio_clock.set_now_seconds(0.5)  # metade do caminho -- fracao 0.5
    system.update(world, delta_time=0.016)
    scale_at_half = float(transform_pool.active_view()["scale_x"][transform_pool.dense_row_of(ring_index)])
    assert scale_at_half == pytest.approx((RING_START_SCALE + RING_END_SCALE) / 2.0)

    null_audio_clock.set_now_seconds(1.0)  # exatamente no hit -- fracao 0.0
    system.update(world, delta_time=0.016)
    scale_at_hit = float(transform_pool.active_view()["scale_x"][transform_pool.dense_row_of(ring_index)])
    assert scale_at_hit == pytest.approx(RING_END_SCALE)


def test_ball_position_interpolates_only_while_tracking(memory_manager, world, null_audio_clock):
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(
        world, OsuObjectKind.SLIDER, timestamp_seconds=1.0,
        x=0.0, y=0.0, end_x=100.0, end_y=200.0, duration_seconds=1.0,
    )
    ball_packed = _spawn_companion(world, x=0.0, y=0.0)
    ball_index = unpack_index(ball_packed)
    note_state_view = world.get_pool(NOTE_STATE_POOL_NAME).active_view()
    note_state_view["ball_entity_id"][row] = ball_packed
    transform_pool = world.get_pool("transform")

    system = _make_system(null_audio_clock)

    # Ainda NAO em tracking -- bola nao deve se mover mesmo com o tempo passando.
    null_audio_clock.set_now_seconds(1.5)
    system.update(world, delta_time=0.016)
    assert float(transform_pool.active_view()["position_x"][transform_pool.dense_row_of(ball_index)]) == 0.0

    # Liga tracking manualmente (simula o que OsuJudgmentSystem faria no clique)
    # -- na METADE do arraste (timestamp 1.0 + duration 1.0 => hit em 2.0, meio-caminho em 1.5).
    note_state_view["is_tracking"][row] = True
    system.update(world, delta_time=0.016)

    ball_row = transform_pool.dense_row_of(ball_index)
    assert float(transform_pool.active_view()["position_x"][ball_row]) == pytest.approx(50.0)
    assert float(transform_pool.active_view()["position_y"][ball_row]) == pytest.approx(100.0)


def test_multiple_circles_and_a_slider_together_do_not_crash_or_cross_contaminate(memory_manager, world, null_audio_clock):
    """Cenario mais realista: varios CIRCLEs (ball sempre NULL) + 1 SLIDER
    (ring e ball reais) ativos ao mesmo tempo -- confirma que o
    mascaramento nao so evita crash como preserva a correspondencia
    correta linha-a-linha entre note_state e as companheiras certas."""
    _register_archetypes(memory_manager, world)
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    transform_pool = world.get_pool("transform")

    circle_rings = []
    for i in range(3):
        _, row = _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=float(i * 10), y=float(i * 10))
        ring_packed = _spawn_companion(world, x=float(i * 10), y=float(i * 10))
        note_state_pool.active_view()["ring_entity_id"][row] = ring_packed
        circle_rings.append((row, ring_packed))

    _, slider_row = _spawn_note(
        world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=100.0, end_y=0.0, duration_seconds=1.0
    )
    slider_ring_packed = _spawn_companion(world, x=500.0, y=500.0)
    note_state_pool.active_view()["ring_entity_id"][slider_row] = slider_ring_packed

    system = _make_system(null_audio_clock)
    null_audio_clock.set_now_seconds(0.5)

    system.update(world, delta_time=0.016)  # nao deve levantar erro

    # Cada anel de circulo deve ter recebido a MESMA escala (todos no mesmo
    # timestamp/approach) -- nao um valor vazado de outra linha.
    scales = [
        float(transform_pool.active_view()["scale_x"][transform_pool.dense_row_of(unpack_index(ring_packed))])
        for _row, ring_packed in circle_rings
    ]
    assert scales[0] == pytest.approx(scales[1]) == pytest.approx(scales[2])
