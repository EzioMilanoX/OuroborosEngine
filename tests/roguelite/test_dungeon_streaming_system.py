# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de DungeonStreamingSystem (Pilar 3): materializacao/desmaterializacao com histerese."""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.world import World
from ouroboros.roguelite.generation.dungeon_generator import DungeonLayout
from ouroboros.roguelite.generation.schemas import ROOM_DTYPE, TILE_DTYPE
from ouroboros.roguelite.systems.dungeon_streaming_system import DungeonStreamingSystem

ACTIVATION_RADIUS = 50.0
DEACTIVATION_RADIUS = 100.0


def _make_layout(centers) -> DungeonLayout:
    rooms = np.zeros(len(centers), dtype=ROOM_DTYPE)
    for i, (center_x, center_y) in enumerate(centers):
        rooms[i] = (i, int(center_x), int(center_y), 1, 1, 0, 0, 0, float(center_x), float(center_y))
    tiles = np.zeros(0, dtype=TILE_DTYPE)
    return DungeonLayout(rooms=rooms, tiles=tiles, seed=0, algorithm_version=1)


def _set_anchor_position(world: World, anchor_packed, x: float, y: float) -> None:
    pool = world.get_pool("transform")
    row = pool.dense_row_of(unpack_index(anchor_packed))
    view = pool.active_view()
    view["position_x"][row] = x
    view["position_y"][row] = y


def _make_world_with_anchor(world: World, start_x: float, start_y: float):
    world.register_archetype("anchor", ("transform",))
    world.register_archetype("room_instance", ("sprite",))
    anchor_packed = world.create_entity("anchor")
    _set_anchor_position(world, anchor_packed, start_x, start_y)
    return anchor_packed


def test_room_within_activation_radius_gets_materialized(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0)])
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed
    )
    world.register_system(system)

    world.step(0.016)

    assert world.get_pool("sprite").count == 1


def test_room_far_from_anchor_stays_dematerialized(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=1000.0, start_y=1000.0)
    layout = _make_layout([(0.0, 0.0)])
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed
    )
    world.register_system(system)

    world.step(0.016)

    assert world.get_pool("sprite").count == 0


def test_room_dematerializes_once_beyond_deactivation_radius(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0)])
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed
    )
    world.register_system(system)

    world.step(0.016)
    assert world.get_pool("sprite").count == 1

    _set_anchor_position(world, anchor_packed, 150.0, 0.0)  # beyond deactivation_radius=100
    world.step(0.016)
    assert world.get_pool("sprite").count == 0


def test_hysteresis_prevents_oscillation_between_activation_and_deactivation_radius(world: World) -> None:
    """Entre activation_radius (50) e deactivation_radius (100) a sala,
    uma vez ativa, deve permanecer ativa -- nao pode oscilar
    criar/destruir a cada frame so por a ancora cruzar repetidamente o
    raio de ativacao."""
    anchor_packed = _make_world_with_anchor(world, start_x=1000.0, start_y=1000.0)
    layout = _make_layout([(0.0, 0.0)])
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed
    )
    world.register_system(system)

    # Ainda fora do raio de ativacao.
    world.step(0.016)
    assert world.get_pool("sprite").count == 0

    # Entra no raio de ativacao (40 < 50) -- materializa.
    _set_anchor_position(world, anchor_packed, 40.0, 0.0)
    world.step(0.016)
    assert world.get_pool("sprite").count == 1

    # Oscila repetidamente numa faixa ENTRE os dois raios (50 < x < 100):
    # nunca deve desmaterializar nem tentar materializar de novo.
    for x in (70.0, 40.0, 70.0, 45.0, 70.0):
        _set_anchor_position(world, anchor_packed, x, 0.0)
        world.step(0.016)
        assert world.get_pool("sprite").count == 1

    # So desmaterializa ao ultrapassar deactivation_radius (100).
    _set_anchor_position(world, anchor_packed, 150.0, 0.0)
    world.step(0.016)
    assert world.get_pool("sprite").count == 0


def test_multiple_rooms_transition_independently(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0), (300.0, 0.0), (600.0, 0.0)])
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed
    )
    world.register_system(system)

    world.step(0.016)
    assert world.get_pool("sprite").count == 1  # somente a sala 0

    _set_anchor_position(world, anchor_packed, 300.0, 0.0)
    world.step(0.016)
    # Sala 0 esta a 300 de distancia (> deactivation_radius) -> desmaterializa;
    # sala 1 esta a 0 de distancia -> materializa; sala 2 a 300 -> nada.
    assert world.get_pool("sprite").count == 1

    _set_anchor_position(world, anchor_packed, 600.0, 0.0)
    world.step(0.016)
    assert world.get_pool("sprite").count == 1


def test_on_room_activated_receives_the_room_row_and_the_new_packed_entity_id(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0)])
    calls = []
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed,
        on_room_activated=lambda room_row, packed_entity_id: calls.append((int(room_row["room_id"]), packed_entity_id)),
    )
    world.register_system(system)

    world.step(0.016)

    assert len(calls) == 1
    room_id, packed_entity_id = calls[0]
    assert room_id == 0
    assert world.get_pool("sprite").is_attached(unpack_index(packed_entity_id))


def test_on_room_deactivated_is_called_before_destroy_with_the_same_packed_entity_id(world: World) -> None:
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0)])
    activated = []
    deactivated = []
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed,
        on_room_activated=lambda room_row, packed_entity_id: activated.append(packed_entity_id),
        on_room_deactivated=lambda room_row, packed_entity_id: deactivated.append(packed_entity_id),
    )
    world.register_system(system)

    world.step(0.016)
    assert len(activated) == 1
    assert deactivated == []

    _set_anchor_position(world, anchor_packed, 150.0, 0.0)  # beyond deactivation_radius=100
    world.step(0.016)

    assert deactivated == [activated[0]]


def test_on_room_activated_fires_again_on_reactivation_since_entities_are_never_reused(world: World) -> None:
    """Reativar uma sala sempre cria uma entidade NOVA e vazia (world.create_entity
    de novo, nunca reaproveita a antiga) -- o callback de ativacao precisa disparar
    de novo a cada reativacao, nao so na primeira vez."""
    anchor_packed = _make_world_with_anchor(world, start_x=0.0, start_y=0.0)
    layout = _make_layout([(0.0, 0.0)])
    calls = []
    system = DungeonStreamingSystem(
        layout, "room_instance", ACTIVATION_RADIUS, DEACTIVATION_RADIUS, "transform", anchor_packed,
        on_room_activated=lambda room_row, packed_entity_id: calls.append(packed_entity_id),
    )
    world.register_system(system)

    world.step(0.016)  # ativa
    _set_anchor_position(world, anchor_packed, 150.0, 0.0)
    world.step(0.016)  # desativa
    _set_anchor_position(world, anchor_packed, 0.0, 0.0)
    world.step(0.016)  # reativa

    assert len(calls) == 2
    assert calls[0] != calls[1]  # entidade nova, PackedEntityId diferente (indice reciclado ou nao)
