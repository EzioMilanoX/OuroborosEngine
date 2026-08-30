# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa TileCollisionSystem: resolucao AABB-vs-grade por eixo, grounded, e o contrato de ordem com PhysicsSystem/GravitySystem."""
from __future__ import annotations

import pytest

from ouroboros.core.grid2d import Grid2D
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.gravity_system import GravitySystem
from ouroboros.core.systems.physics_system import PhysicsSystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem

ARCHETYPE_NAME = "body"
CELL_SIZE = 32.0
# Precisa bater com DEFAULT_TEST_ENTITY_CAPACITY (tests/conftest.py): o array de
# scratch de TileCollisionSystem e indexado por entity_index GLOBAL (administrado
# pelo free-list do MemoryManager por tras da fixture `memory_manager`), nao pela
# capacidade local de nenhuma pool -- um valor menor causa IndexError assim que o
# free-list entrega um indice alto (ele desempilha do topo). Mesmo criterio de
# tests/rhythm/test_judgment_system.py.
ENTITY_CAPACITY = 1024


def _make_grid(cols: int = 10, rows: int = 10) -> Grid2D:
    return Grid2D(cols=cols, rows=rows, cell_size=CELL_SIZE)


def _spawn_body(world, x: float, y: float, vx: float, vy: float, half_width: float = 8.0, half_height: float = 8.0):
    packed = world.create_entity(ARCHETYPE_NAME)
    index = unpack_index(packed)

    transform_pool = world.get_pool("transform")
    t_row = transform_pool.dense_row_of(index)
    t_view = transform_pool.active_view()
    t_view["position_x"][t_row] = x
    t_view["position_y"][t_row] = y

    velocity_pool = world.get_pool("velocity")
    v_row = velocity_pool.dense_row_of(index)
    v_view = velocity_pool.active_view()
    v_view["linear_x"][v_row] = vx
    v_view["linear_y"][v_row] = vy

    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = half_width
    h_view["half_height"][h_row] = half_height

    return packed, index


@pytest.fixture
def registered_world(world):
    world.register_archetype(ARCHETYPE_NAME, ("transform", "velocity", "hitbox"))
    return world


def _positions(world, index):
    transform_pool = world.get_pool("transform")
    row = transform_pool.dense_row_of(index)
    view = transform_pool.active_view()
    return float(view["position_x"][row]), float(view["position_y"][row])


def _velocities(world, index):
    velocity_pool = world.get_pool("velocity")
    row = velocity_pool.dense_row_of(index)
    view = velocity_pool.active_view()
    return float(view["linear_x"][row]), float(view["linear_y"][row])


def test_falls_freely_when_nothing_solid_is_nearby(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    _packed, index = _spawn_body(world, x=16.0, y=16.0, vx=0.0, vy=50.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)

    _x, y = _positions(world, index)
    assert y == pytest.approx(16.0 + 5.0)
    assert tile_system.is_grounded(index) is False


def test_lands_on_solid_ground_and_reports_grounded(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    grid.cells[5, :] = 1  # linha 5 solida inteira -> y em [160, 192)
    _packed, index = _spawn_body(world, x=16.0, y=150.0, vx=0.0, vy=200.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # sem colisao, iria pra 150+20=170 (dentro da linha solida)

    _x, y = _positions(world, index)
    assert y == pytest.approx(152.0)  # 160 (borda superior da celula) - 8 (half_height)
    _vx, vy = _velocities(world, index)
    assert vy == pytest.approx(0.0)
    assert tile_system.is_grounded(index) is True


def test_hitting_a_ceiling_stops_upward_motion_without_reporting_grounded(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    grid.cells[3, :] = 1  # linha 3 solida -> y em [96, 128)
    _packed, index = _spawn_body(world, x=16.0, y=140.0, vx=0.0, vy=-200.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # sem colisao, iria pra 140-20=120 (dentro da linha solida)

    _x, y = _positions(world, index)
    assert y == pytest.approx(136.0)  # 128 (borda inferior da celula) + 8 (half_height)
    _vx, vy = _velocities(world, index)
    assert vy == pytest.approx(0.0)
    assert tile_system.is_grounded(index) is False  # bateu de baixo pra cima, nao "pousou"


def test_stops_against_a_wall_when_moving_right(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    grid.cells[:, 5] = 1  # coluna 5 solida -> x em [160, 192)
    _packed, index = _spawn_body(world, x=140.0, y=16.0, vx=300.0, vy=0.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # sem colisao, iria pra 140+30=170 (dentro da coluna solida)

    x, _y = _positions(world, index)
    assert x == pytest.approx(152.0)  # 160 (borda esquerda da celula) - 8 (half_width)
    vx, _vy = _velocities(world, index)
    assert vx == pytest.approx(0.0)


def test_stops_against_a_wall_when_moving_left(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    grid.cells[:, 5] = 1  # coluna 5 solida -> x em [160, 192)
    _packed, index = _spawn_body(world, x=210.0, y=16.0, vx=-300.0, vy=0.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # sem colisao, iria pra 210-30=180 (dentro da coluna solida)

    x, _y = _positions(world, index)
    assert x == pytest.approx(200.0)  # 192 (borda direita da celula) + 8 (half_width)
    vx, _vy = _velocities(world, index)
    assert vx == pytest.approx(0.0)


def test_stationary_axis_is_never_resolved(memory_manager, registered_world):
    """Uma entidade parada num eixo (velocidade zero) nao pode ter entrado
    numa celula solida NESTE frame por causa dele -- nao deve ser testada."""
    world = registered_world
    grid = _make_grid()
    grid.cells[:, :] = 1  # tudo solido -- se o eixo X fosse testado mesmo parado, isso quebraria
    grid.cells[0, 0] = 0  # exceto a celula onde a entidade ja esta (repouso valido)
    _packed, index = _spawn_body(world, x=16.0, y=16.0, vx=0.0, vy=0.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # nao deve levantar nem mover nada

    x, y = _positions(world, index)
    assert x == pytest.approx(16.0)
    assert y == pytest.approx(16.0)


def test_diagonal_movement_into_a_corner_resolves_independently_per_axis(memory_manager, registered_world):
    """Movendo na diagonal contra um canto em L: o eixo X e resolvido usando
    a posicao Y ANTIGA (nao a nova) -- prova que nao "pega" a quina."""
    world = registered_world
    grid = _make_grid()
    grid.cells[5, 5] = 1  # unica celula solida, num canto -- x em [160,192), y em [160,192)
    # entidade um pouco acima-esquerda da celula solida, movendo pra
    # baixo-direita rapido o bastante pra, sem resolucao por eixo, acabar
    # dentro dela nos dois eixos ao mesmo tempo.
    _packed, index = _spawn_body(world, x=145.0, y=145.0, vx=300.0, vy=300.0)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)

    world.step(0.1)  # sem colisao, iria pra (175, 175) -- dentro da celula solida nos 2 eixos

    x, y = _positions(world, index)
    # X foi resolvido usando prev_y=145 (fora da celula solida na linha 5? 145 -> row=4,
    # ainda nao entrou na linha solida) -- ambos os eixos acabam colidindo aqui pois a
    # entidade se aproxima o bastante; o importante e que a posicao final nunca fica
    # DENTRO da celula solida em nenhum dos dois eixos.
    assert not bool(grid.is_solid([x], [y])[0])


def test_oversized_hitbox_raises_value_error(memory_manager, registered_world):
    world = registered_world
    grid = _make_grid()
    _packed, index = _spawn_body(world, x=16.0, y=16.0, vx=10.0, vy=0.0, half_width=CELL_SIZE, half_height=8.0)
    world.register_system(PhysicsSystem(memory_manager))
    world.register_system(TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY))

    with pytest.raises(ValueError):
        world.step(0.1)


def test_grounded_self_sustains_every_frame_at_rest_with_gravity_registered(memory_manager, registered_world):
    """Prova de ponta a ponta da ordem PhysicsSystem -> TileCollisionSystem ->
    GravitySystem: uma entidade em repouso deve reportar grounded=True em
    TODO frame subsequente, nunca oscilando (mesmo achado da critica do M12)."""
    world = registered_world
    grid = _make_grid()
    grid.cells[5, :] = 1  # linha 5 solida -> y em [160, 192)
    # spawna JA encostada no chao (y=152 = 160-8), com uma velocidade_y inicial
    # pequena e nao-nula (documentado como responsabilidade do produto).
    _packed, index = _spawn_body(world, x=16.0, y=152.0, vx=0.0, vy=1e-3)
    world.register_system(PhysicsSystem(memory_manager))
    tile_system = TileCollisionSystem(memory_manager, grid, ENTITY_CAPACITY)
    world.register_system(tile_system)
    world.register_system(GravitySystem(memory_manager, gravity_y=500.0))

    for _ in range(10):
        world.step(1.0 / 60.0)
        assert tile_system.is_grounded(index) is True

    x, y = _positions(world, index)
    assert x == pytest.approx(16.0)
    assert y == pytest.approx(152.0)
