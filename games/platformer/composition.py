# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao do Platformer: carrega o nivel, monta o World (com TileCollisionSystem/GravitySystem via CompositionRoot), e registra jogador/sistemas por cima."""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader

from games.platformer.level import Level, load_level
from games.platformer.systems.player_jump_system import PlayerJumpSystem
from games.platformer.systems.player_run_system import PlayerRunSystem
from games.platformer.systems.quit_on_action_system import QuitOnActionSystem

PLAYER_ARCHETYPE_NAME = "player"
TILE_BACKDROP_ARCHETYPE_NAME = "tile_backdrop"

_GAME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GAME_DIR.parent.parent
PLATFORMER_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "platformer"

CELL_SIZE = 32.0
GRAVITY_Y = 900.0
MOVE_SPEED = 160.0
JUMP_VELOCITY_Y = -360.0
# Spawn com velocity_y inicial pequena e NAO-nula (nao 0.0) -- documentado em
# TileCollisionSystem.is_grounded: cada eixo so e testado se a velocidade
# NAQUELE eixo for diferente de zero, entao um spawn com velocity_y == 0.0
# faria o eixo Y ser pulado por inteiro no 1o update(), reportando "no ar"
# mesmo estando em repouso sobre o chao.
INITIAL_VELOCITY_Y = 1e-3


def _find_tile_collision_system(world: World) -> TileCollisionSystem:
    """`CompositionRoot.build()` ja registra um `TileCollisionSystem` quando
    `tile_grid` e passado -- `PlayerJumpSystem` precisa da MESMA instancia
    (pra consultar `is_grounded()` do frame corrente), nunca uma segunda
    construida a parte. Mesmo idioma de `_find_collision_system` no
    Roguelite (`games/roguelite/composition.py`)."""
    for system in world.systems:
        if isinstance(system, TileCollisionSystem):
            return system
    raise RuntimeError("CompositionRoot.build() deveria ter registrado um TileCollisionSystem")


def _spawn_player(world: World, spawn_x: float, spawn_y: float) -> int:
    packed_entity_id = world.create_entity(PLAYER_ARCHETYPE_NAME)
    index = unpack_index(packed_entity_id)

    transform_pool = world.get_pool("transform")
    t_row = transform_pool.dense_row_of(index)
    t_view = transform_pool.active_view()
    t_view["position_x"][t_row] = spawn_x
    t_view["position_y"][t_row] = spawn_y
    t_view["rotation_rad"][t_row] = 0.0
    t_view["scale_x"][t_row] = 1.0
    t_view["scale_y"][t_row] = 1.0

    velocity_pool = world.get_pool("velocity")
    v_row = velocity_pool.dense_row_of(index)
    v_view = velocity_pool.active_view()
    v_view["linear_x"][v_row] = 0.0
    v_view["linear_y"][v_row] = INITIAL_VELOCITY_Y
    v_view["angular"][v_row] = 0.0

    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = 10.0
    h_view["half_height"][h_row] = 14.0
    h_view["collision_layer"][h_row] = 1
    h_view["collision_mask"][h_row] = 0

    sprite_pool = world.get_pool("sprite")
    s_row = sprite_pool.dense_row_of(index)
    s_view = sprite_pool.active_view()
    s_view["texture_id"][s_row] = SHAPE_CIRCLE
    s_view["tint_r"][s_row] = 90
    s_view["tint_g"][s_row] = 160
    s_view["tint_b"][s_row] = 255
    s_view["tint_a"][s_row] = 255
    s_view["layer_z"][s_row] = 20

    return index


def _spawn_tile_backdrops(world: World, level: Level, cell_size: float) -> None:
    """Entidades PURAMENTE visuais, uma por celula solida -- a colisao de
    verdade e contra `level.grid` (`TileCollisionSystem`), nunca contra a
    hitbox de nenhuma dessas entidades (o arquetipo nem tem hitbox)."""
    transform_pool = world.get_pool("transform")
    sprite_pool = world.get_pool("sprite")
    for center_x, center_y in level.solid_cell_centers:
        packed_entity_id = world.create_entity(TILE_BACKDROP_ARCHETYPE_NAME)
        index = unpack_index(packed_entity_id)

        t_row = transform_pool.dense_row_of(index)
        t_view = transform_pool.active_view()
        t_view["position_x"][t_row] = center_x
        t_view["position_y"][t_row] = center_y
        t_view["rotation_rad"][t_row] = 0.0
        t_view["scale_x"][t_row] = cell_size / 8.0
        t_view["scale_y"][t_row] = cell_size / 8.0

        s_row = sprite_pool.dense_row_of(index)
        s_view = sprite_pool.active_view()
        s_view["texture_id"][s_row] = SHAPE_RECT
        s_view["tint_r"][s_row] = 90
        s_view["tint_g"][s_row] = 70
        s_view["tint_b"][s_row] = 60
        s_view["tint_a"][s_row] = 255
        s_view["layer_z"][s_row] = 0


def build_game(config: EngineConfig) -> GameLoop:
    """
    Monta o Platformer completo: carrega o nivel ASCII hardcoded
    (`Grid2D` + ponto de spawn, ja validado -- ver `level.py`), passa a
    grade pro `CompositionRoot` montar `TileCollisionSystem`/
    `GravitySystem` (Pilar 1, ROADMAP M12), registra por cima o
    arquetipo/jogador/backdrop visual/sistemas especificos deste jogo, e
    retorna um `GameLoop` pronto para `.run()`.
    """
    level = load_level(cell_size=CELL_SIZE)

    game_loop = CompositionRoot(config).build(tile_grid=level.grid, gravity_y=GRAVITY_Y)
    world = game_loop.world

    # Carrega data/archetypes/platformer/*.json de verdade (nao um tuple hardcoded
    # em Python) -- so usa pools genericas (Pilar 1), ja criadas por CompositionRoot.
    ArchetypeLoader(PLATFORMER_ARCHETYPES_DIR).load_and_register_all(world)

    player_index = _spawn_player(world, level.spawn_x, level.spawn_y)
    _spawn_tile_backdrops(world, level, CELL_SIZE)

    tile_collision_system = _find_tile_collision_system(world)

    world.register_system(PlayerRunSystem(game_loop.input_provider, MOVE_SPEED, player_index))
    world.register_system(
        PlayerJumpSystem(game_loop.input_provider, tile_collision_system, JUMP_VELOCITY_Y, player_index)
    )
    world.register_system(QuitOnActionSystem(game_loop.input_provider, game_loop))

    return game_loop
