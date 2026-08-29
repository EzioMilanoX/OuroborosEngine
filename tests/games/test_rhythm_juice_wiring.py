"""Testes de M11.3/M11.4 (particula no acerto, screen shake no erro, textura/forma por camada)."""
from __future__ import annotations

import pytest

from ouroboros.bootstrap.screen_shake import ScreenShake
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.particle_storage import ParticleStorage
from ouroboros.interfaces.renderer import SHAPE_RING
from ouroboros.rhythm.runtime.judgment_system import Judgment

from games.rhythm_game.composition import (
    LAYER_PARTICLE_TINTS,
    LAYER_VOCAL,
    MISS_SHAKE_CAP,
    MISS_SHAKE_INTENSITY,
    NOTE_TEXTURE_ID,
    _make_on_judgment,
    _make_on_note_spawned,
)

LANE_X_POSITIONS = (100.0, 200.0, 300.0, 400.0)
JUDGMENT_LINE_Y = 500.0


def _make_judgment_callback(rng=None):
    storage = ParticleStorage(capacity=64)
    shake = ScreenShake(rng=rng)
    return storage, shake, _make_on_judgment(storage, shake, LANE_X_POSITIONS, JUDGMENT_LINE_Y)


def test_perfect_hit_emits_a_particle_burst_at_the_hit_lanes_position():
    storage, _shake, on_judgment = _make_judgment_callback()

    on_judgment(Judgment.PERFECT, 0, 2)

    assert storage.count > 0
    view = storage.active_view()
    assert (view["position_x"] == LANE_X_POSITIONS[2]).all()
    assert (view["position_y"] == JUDGMENT_LINE_Y).all()


def test_good_hit_also_emits_a_particle_burst():
    storage, _shake, on_judgment = _make_judgment_callback()

    on_judgment(Judgment.GOOD, 0, 0)

    assert storage.count > 0


def test_burst_color_matches_the_notes_layer():
    storage, _shake, on_judgment = _make_judgment_callback()

    on_judgment(Judgment.PERFECT, LAYER_VOCAL, 1)

    view = storage.active_view()
    expected = LAYER_PARTICLE_TINTS[LAYER_VOCAL]
    assert int(view["tint_r"][0]) == expected[0]
    assert int(view["tint_g"][0]) == expected[1]
    assert int(view["tint_b"][0]) == expected[2]


def test_unknown_layer_falls_back_to_the_kick_tint():
    storage, _shake, on_judgment = _make_judgment_callback()

    on_judgment(Judgment.PERFECT, 99, 0)

    view = storage.active_view()
    expected = LAYER_PARTICLE_TINTS[0]
    assert int(view["tint_r"][0]) == expected[0]


def test_miss_never_emits_a_particle_but_triggers_screen_shake():
    storage, shake, on_judgment = _make_judgment_callback(rng=lambda: 1.0)

    on_judgment(Judgment.MISS, 0, -1)

    assert storage.count == 0
    assert shake.current_magnitude() == MISS_SHAKE_INTENSITY


def test_repeated_misses_stack_additively_up_to_the_cap():
    _storage, shake, on_judgment = _make_judgment_callback(rng=lambda: 1.0)

    on_judgment(Judgment.MISS, 0, -1)
    on_judgment(Judgment.MISS, 0, -1)

    assert shake.current_magnitude() == pytest.approx(min(2 * MISS_SHAKE_INTENSITY, MISS_SHAKE_CAP))

    for _ in range(10):
        on_judgment(Judgment.MISS, 0, -1)

    assert shake.current_magnitude() == MISS_SHAKE_CAP


def test_a_sentinel_lane_index_on_a_hit_is_ignored_defensively():
    """PERFECT/GOOD sempre vem de _judge_presses (lane_index >= 0 sempre) --
    mas se algo repassar o sentinela -1 por engano, nao deve emitir particula
    (nao ha posicao de lane valida pra desenhar o burst)."""
    storage, _shake, on_judgment = _make_judgment_callback()

    on_judgment(Judgment.PERFECT, 0, -1)

    assert storage.count == 0


def _spawn_note(world):
    world.register_archetype("note", ("transform", "sprite"))
    packed = world.create_entity("note")
    return packed, unpack_index(packed)


def test_kick_layer_notes_use_the_real_note_texture(world):
    packed, index = _spawn_note(world)
    on_note_spawned = _make_on_note_spawned()

    on_note_spawned(world, packed, lane=0, threat_type=0, layer=0)

    sprite_pool = world.get_pool("sprite")
    row = sprite_pool.dense_row_of(index)
    assert int(sprite_pool.active_view()["texture_id"][row]) == NOTE_TEXTURE_ID


def test_vocal_layer_notes_use_shape_ring_instead_of_the_texture(world):
    packed, index = _spawn_note(world)
    on_note_spawned = _make_on_note_spawned()

    on_note_spawned(world, packed, lane=0, threat_type=0, layer=LAYER_VOCAL)

    sprite_pool = world.get_pool("sprite")
    row = sprite_pool.dense_row_of(index)
    assert int(sprite_pool.active_view()["texture_id"][row]) == SHAPE_RING
