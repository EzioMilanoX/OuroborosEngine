# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao do Tactics: monta o campo de batalha hardcoded, as unidades, e a TacticsBattleScene por cima do CompositionRoot generico."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.tactics.combat.schemas import TACTICS_UNIT_DTYPE, Team
from ouroboros.tactics.grid.battlefield_grid import BattlefieldGrid
from ouroboros.tactics.grid.schemas import TerrainType
from ouroboros.tactics.turn_queue import TurnQueue

from games.tactics.battle_scene import TacticsBattleScene, rebuild_occupancy_from_pool

UNIT_ARCHETYPE_NAME = "tactics_unit"
TERRAIN_ARCHETYPE_NAME = "terrain_backdrop"
UNIT_POOL_NAME = "tactics_unit"

_GAME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GAME_DIR.parent.parent
TACTICS_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "tactics"

CELL_SIZE = 48.0
BATTLEFIELD_COLS = 10
BATTLEFIELD_ROWS = 8

# Limite superior de folga usado como clamp "sem teto pratico" pros atributos
# de unidade -- mesmo idioma de WeaponLoader._UNBOUNDED_MAX.
_UNBOUNDED_MAX = float(np.finfo(np.float32).max)


@dataclass(frozen=True)
class UnitDefinition:
    name: str
    team: int
    grid_x: int
    grid_y: int
    max_hp: float
    attack: float
    defense: float
    move_range: float
    initiative: float
    tint_rgba: Tuple[int, int, int, int]


# Roster hardcoded (1 nivel/roster nao justifica um loader data-driven ainda --
# ver ROADMAP M13, "fora de escopo: loader data-driven de mapa de batalha").
# Iniciativa deliberadamente ENTRELACADA entre os dois times (Scout > Warrior >
# Grunts), nao "todo o time do jogador primeiro" -- prova que o sort de
# TurnQueue realmente importa.
UNIT_DEFINITIONS: Tuple[UnitDefinition, ...] = (
    UnitDefinition("Warrior", Team.PLAYER, 1, 4, 20.0, 6.0, 2.0, 3.0, 2.0, (90, 160, 255, 255)),
    UnitDefinition("Scout", Team.PLAYER, 1, 3, 12.0, 4.0, 0.0, 5.0, 3.0, (90, 220, 160, 255)),
    UnitDefinition("Grunt A", Team.ENEMY, 8, 3, 10.0, 3.0, 1.0, 3.0, 1.0, (220, 90, 90, 255)),
    UnitDefinition("Grunt B", Team.ENEMY, 8, 5, 10.0, 3.0, 1.0, 3.0, 1.0, (220, 90, 90, 255)),
)


def _build_battlefield() -> BattlefieldGrid:
    """Um muro no meio (coluna 5) com uma unica brecha (linha 4) + duas
    celulas de terreno DIFFICULT -- o bastante pra exercitar pathfinding/
    alcancaveis/linha de visao de verdade, sem exigir um formato de nivel
    data-driven (1 mapa hardcoded nao justifica isso ainda)."""
    grid = BattlefieldGrid(cols=BATTLEFIELD_COLS, rows=BATTLEFIELD_ROWS)
    for y in range(BATTLEFIELD_ROWS):
        if y != 4:
            grid.set_cell(5, y, TerrainType.BLOCKED)
    grid.set_cell(2, 2, TerrainType.DIFFICULT, move_cost=2.0)
    grid.set_cell(7, 5, TerrainType.DIFFICULT, move_cost=2.0)
    return grid


def _spawn_unit(world: World, modifier_stack: ModifierStack, definition: UnitDefinition) -> int:
    packed_entity_id = world.create_entity(UNIT_ARCHETYPE_NAME)
    index = unpack_index(packed_entity_id)

    unit_pool = world.get_pool(UNIT_POOL_NAME)
    u_row = unit_pool.dense_row_of(index)
    u_view = unit_pool.active_view()
    u_view["team"][u_row] = definition.team
    u_view["grid_x"][u_row] = definition.grid_x
    u_view["grid_y"][u_row] = definition.grid_y
    u_view["current_hp"][u_row] = definition.max_hp
    u_view["max_hp"][u_row] = definition.max_hp
    u_view["attack_attribute_index"][u_row] = modifier_stack.register_attribute(
        base_value=definition.attack, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
    )
    u_view["defense_attribute_index"][u_row] = modifier_stack.register_attribute(
        base_value=definition.defense, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
    )
    u_view["move_range_attribute_index"][u_row] = modifier_stack.register_attribute(
        base_value=definition.move_range, min_clamp=0.0, max_clamp=_UNBOUNDED_MAX
    )

    transform_pool = world.get_pool("transform")
    t_row = transform_pool.dense_row_of(index)
    t_view = transform_pool.active_view()
    t_view["position_x"][t_row] = (definition.grid_x + 0.5) * CELL_SIZE
    t_view["position_y"][t_row] = (definition.grid_y + 0.5) * CELL_SIZE
    t_view["rotation_rad"][t_row] = 0.0
    t_view["scale_x"][t_row] = 1.0
    t_view["scale_y"][t_row] = 1.0

    sprite_pool = world.get_pool("sprite")
    s_row = sprite_pool.dense_row_of(index)
    s_view = sprite_pool.active_view()
    s_view["texture_id"][s_row] = SHAPE_CIRCLE
    s_view["tint_r"][s_row] = definition.tint_rgba[0]
    s_view["tint_g"][s_row] = definition.tint_rgba[1]
    s_view["tint_b"][s_row] = definition.tint_rgba[2]
    s_view["tint_a"][s_row] = definition.tint_rgba[3]
    s_view["layer_z"][s_row] = 10

    return index


def _spawn_terrain_backdrops(world: World, grid: BattlefieldGrid) -> None:
    """Entidades PURAMENTE visuais, uma por celula nao-WALKABLE -- a
    logica de verdade consulta `BattlefieldGrid.terrain_type_at`, nunca
    essas entidades (mesmo espirito do backdrop de tile do Platformer)."""
    transform_pool = world.get_pool("transform")
    sprite_pool = world.get_pool("sprite")
    for y in range(grid.rows):
        for x in range(grid.cols):
            terrain = grid.terrain_type_at(x, y)
            if terrain == TerrainType.WALKABLE:
                continue

            packed_entity_id = world.create_entity(TERRAIN_ARCHETYPE_NAME)
            index = unpack_index(packed_entity_id)

            t_row = transform_pool.dense_row_of(index)
            t_view = transform_pool.active_view()
            t_view["position_x"][t_row] = (x + 0.5) * CELL_SIZE
            t_view["position_y"][t_row] = (y + 0.5) * CELL_SIZE
            t_view["rotation_rad"][t_row] = 0.0
            t_view["scale_x"][t_row] = CELL_SIZE / 8.0
            t_view["scale_y"][t_row] = CELL_SIZE / 8.0

            s_row = sprite_pool.dense_row_of(index)
            s_view = sprite_pool.active_view()
            s_view["texture_id"][s_row] = SHAPE_RECT
            tint = (60, 60, 70, 255) if terrain == TerrainType.BLOCKED else (150, 140, 60, 255)
            s_view["tint_r"][s_row] = tint[0]
            s_view["tint_g"][s_row] = tint[1]
            s_view["tint_b"][s_row] = tint[2]
            s_view["tint_a"][s_row] = tint[3]
            s_view["layer_z"][s_row] = 0


def build_game(config: EngineConfig) -> GameLoop:
    """
    Monta o Tactics completo: constroi o campo de batalha hardcoded
    (`BattlefieldGrid`), o `World` generico (Pilar 1/2, via
    `CompositionRoot.build()` -- nenhuma entidade aqui usa `velocity`/
    `hitbox`, entao `PhysicsSystem`/`CollisionSystem` (sempre registrados)
    ficam no-op), o roster hardcoded de unidades (atributos de
    ataque/defesa/alcance via um UNICO `ModifierStack` compartilhado,
    mesmo idioma do sistema de arma do Roguelite), o `TurnQueue` (ordenado
    por iniciativa ENTRELACADA entre os times), e substitui a pilha de
    cenas por uma `TacticsBattleScene` ANTES do primeiro frame (mesmo
    truque de `MenuScene`/M8c -- a `GameplayScene` base nunca chega a
    rodar `world.step()` nem uma vez, e de fato NUNCA vai rodar aqui,
    ja que `TacticsBattleScene` nunca chama `world.step()`).
    """
    grid = _build_battlefield()

    game_loop = CompositionRoot(config).build()
    world = game_loop.world

    world.create_pool(UNIT_POOL_NAME, TACTICS_UNIT_DTYPE, dense_capacity=config.entity_capacity)
    ArchetypeLoader(TACTICS_ARCHETYPES_DIR).load_and_register_all(world)

    modifier_stack = ModifierStack(attribute_capacity=len(UNIT_DEFINITIONS) * 3, entry_capacity=8)

    entity_indices = []
    initiative_values = []
    for definition in UNIT_DEFINITIONS:
        index = _spawn_unit(world, modifier_stack, definition)
        entity_indices.append(index)
        initiative_values.append(definition.initiative)

    # Nenhum modificador e empurrado no v1 (roster fixo, sem buffs/debuffs de
    # terreno/habilidade ainda) -- recompute_all() aqui e defensivo/redundante
    # (register_attribute ja escreve final_value correto sozinho), mas
    # documenta o contrato: como TacticsBattleScene NUNCA chama world.step()
    # (entao ModifierApplicationSystem, mesmo se registrado, nunca rodaria),
    # qualquer push() futuro de um buff PRECISARIA chamar recompute_all()
    # direto, manualmente, na hora -- nao ha mais ninguem que va fazer isso.
    modifier_stack.recompute_all()

    turn_queue = TurnQueue(capacity=len(UNIT_DEFINITIONS))
    turn_queue.build(entity_indices, initiative_values)

    rebuild_occupancy_from_pool(world, grid)
    _spawn_terrain_backdrops(world, grid)

    battle_scene = TacticsBattleScene(
        input_provider=game_loop.input_provider,
        game_loop=game_loop,
        grid=grid,
        modifier_stack=modifier_stack,
        turn_queue=turn_queue,
        viewport_size=(config.window_width, config.window_height),
    )
    game_loop.reset_scenes(battle_scene)

    return game_loop
