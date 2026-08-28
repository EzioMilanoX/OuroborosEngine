"""Composicao do Jogo Roguelite: registra pools/arquetipos/sistemas especificos por cima do CompositionRoot generico."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Tuple

import numpy as np

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.stable_id import stable_id_from_name
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.core.systems.spatial_grid import UniformGrid
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT
from ouroboros.roguelite.combat.schemas import EntityKind, HEALTH_DTYPE
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.roguelite.generation.dungeon_generator import DungeonGenerator, DungeonLayout
from ouroboros.roguelite.generation.random import RandomStreamPurpose, StrictRandom
from ouroboros.roguelite.items.inventory_pool import InventoryPool
from ouroboros.roguelite.items.schemas import INVENTORY_SLOT_DTYPE
from ouroboros.roguelite.items.weapon_loader import WeaponLoader
from ouroboros.roguelite.loaders.difficulty_loader import DifficultyLoader
from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack
from ouroboros.roguelite.systems.damage_system import DamageOnCollisionSystem
from ouroboros.roguelite.systems.dungeon_streaming_system import DungeonStreamingSystem
from ouroboros.roguelite.systems.modifier_application_system import ModifierApplicationSystem

from games.roguelite.end_scene import EndScene
from games.roguelite.hud import build_hud_callback
from games.roguelite.schemas import FACING_DTYPE
from games.roguelite.systems.enemy_chase_system import EnemyChaseSystem
from games.roguelite.systems.game_over_on_death_system import GameOverOnDeathSystem
from games.roguelite.systems.player_movement_system import PlayerMovementSystem
from games.roguelite.systems.quit_on_action_system import QuitOnActionSystem
from games.roguelite.systems.weapon_fire_system import WeaponFireSystem

HEALTH_POOL_NAME = "health"
FACING_POOL_NAME = "facing"
INVENTORY_POOL_NAME = "inventory_slot"

# Camadas de colisao (bitmask): jogador so colide com inimigo; inimigo colide com
# jogador E projetil; projetil so colide com inimigo (nunca com quem o disparou).
LAYER_PLAYER = 1
LAYER_ENEMY = 2
LAYER_PROJECTILE = 4

PLAYER_ARCHETYPE_NAME = "player"
ENEMY_ARCHETYPE_NAME = "enemy_goblin"
PROJECTILE_ARCHETYPE_NAME = "projectile"
ROOM_BACKDROP_ARCHETYPE_NAME = "room_backdrop"

PLAYER_MOVE_SPEED = 180.0
ENEMY_CHASE_SPEED = 90.0
PLAYER_MAX_HP = 100.0
PROJECTILE_HALF_EXTENT = 3.0

# Escala world-space (pixels por unidade de grade da masmorra) -- puramente de
# apresentacao, nao afeta a geracao/reprodutibilidade do DungeonLayout em si.
TILE_PIXELS = 24.0

DUNGEON_ROOT_SEED = 20260827
DUNGEON_LEVEL_SEED = 1
DUNGEON_MAX_ROOMS = 6
DUNGEON_ROOM_SIZE_RANGE = (6, 10)

# UniformGrid (ROADMAP M9.1): celula = 2 tiles, folga de 1 tile alem do tile
# mais externo de verdade (cobre hitboxes que ultrapassam ligeiramente a
# borda -- o bounds em si ja vem dos tiles reais, rooms+corredores, entao
# nao precisa "adivinhar" o quao longe um corredor pode ir).
GRID_CELL_SIZE = TILE_PIXELS * 2
GRID_BOUNDS_MARGIN = TILE_PIXELS
GRID_MAX_CANDIDATE_PAIRS = 4096

# DungeonStreamingSystem (ROADMAP M9.2): a camera centraliza no jogador
# (build_hud_callback) sobre um viewport de ate 800x600 (metade = 400px) --
# ativa a sala assim que sua borda mais proxima PODERIA entrar em quadro
# (raio ate o CENTRO da sala, entao soma a metade do maior lado possivel de
# uma sala: 10 tiles/2 * TILE_PIXELS = 120px) mais uma folga; desativa bem
# mais longe pra nao oscilar nas bordas (histerese).
ROOM_ACTIVATION_RADIUS = 650.0
ROOM_DEACTIVATION_RADIUS = 900.0

_GAME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GAME_DIR.parent.parent
DIFFICULTY_ID = "normal"
DIFFICULTIES_DIR = _REPO_ROOT / "data" / "difficulties"
WEAPONS_DIR = _REPO_ROOT / "data" / "weapons"
STARTER_WEAPON_ID = "starter_pistol"
ROGUELITE_ARCHETYPES_DIR = _REPO_ROOT / "data" / "archetypes" / "roguelite"


def _find_collision_system(world: World) -> CollisionSystem:
    """`CompositionRoot.build()` ja registra um `CollisionSystem` (Pilar 1) --
    `DamageOnCollisionSystem` precisa da MESMA instancia (pra ler
    `get_collision_pairs()` do frame corrente), nunca uma segunda construida a
    parte (rodaria a deteccao em dobro). `World.systems` (ROADMAP M6 --
    adicionado por essa necessidade real) expoe os sistemas ja registrados."""
    for system in world.systems:
        if isinstance(system, CollisionSystem):
            return system
    raise RuntimeError("CompositionRoot.build() deveria ter registrado um CollisionSystem")


def _world_bounds_from_tiles(layout: DungeonLayout) -> Tuple[float, float, float, float]:
    """Limites de verdade do dungeon gerado (salas + corredores), em pixels,
    a partir dos tiles REAIS (nao so do retangulo de cada sala -- corredores
    entre salas distantes podem se estender bem alem dele, ver
    `DungeonGenerator._carve_corridor`). Cada tile e local a sua sala dona
    (`tiles["room_id"]`); soma-se `rooms["grid_x"/"grid_y"]` da sala dona
    pra obter a coordenada global antes de escalar por `TILE_PIXELS`."""
    tiles = layout.tiles
    rooms = layout.rooms
    global_tile_x = rooms["grid_x"][tiles["room_id"]] + tiles["local_x"]
    global_tile_y = rooms["grid_y"][tiles["room_id"]] + tiles["local_y"]
    min_x = float(global_tile_x.min()) * TILE_PIXELS - GRID_BOUNDS_MARGIN
    max_x = float(global_tile_x.max() + 1) * TILE_PIXELS + GRID_BOUNDS_MARGIN
    min_y = float(global_tile_y.min()) * TILE_PIXELS - GRID_BOUNDS_MARGIN
    max_y = float(global_tile_y.max() + 1) * TILE_PIXELS + GRID_BOUNDS_MARGIN
    return (min_x, min_y, max_x, max_y)


def _layout_with_pixel_space_centers(layout: DungeonLayout) -> DungeonLayout:
    """`ROOM_DTYPE.center_x/center_y` sao gerados em unidades de TILE (o
    gerador de masmorra nunca conhece pixels -- so este script de composicao
    escala por `TILE_PIXELS`). `DungeonStreamingSystem` compara `center_x/y`
    direto contra a posicao (em pixels) da entidade-ancora -- sem essa
    conversao, a distancia calculada ficaria errada por um fator de
    `TILE_PIXELS`. So os campos usados pelo streaming mudam; `_spawn_player`/
    `_spawn_enemy` continuam lendo o `layout` ORIGINAL (em tiles) e fazendo
    sua propria escala, como ja faziam."""
    rooms_px = layout.rooms.copy()
    rooms_px["center_x"] *= TILE_PIXELS
    rooms_px["center_y"] *= TILE_PIXELS
    return dataclasses.replace(layout, rooms=rooms_px)


def _make_on_room_activated(world: World):
    """Escreve os campos iniciais (`ArchetypeLoader` ignora `"initial_values"`
    -- achado do M6) da entidade de fundo que acabou de materializar pra UMA
    sala: mesmo retangulo grande de antes, so que agora por ativacao em vez
    de uma vez so no boot.

    `room_row` vem de `DungeonLayout.rooms` -- mas do layout JA ESCALADO
    (`_layout_with_pixel_space_centers`) que e passado pro
    `DungeonStreamingSystem`, entao `center_x`/`center_y` aqui JA estao em
    pixels (nao multiplicar de novo por `TILE_PIXELS` -- faria a sala
    aparecer 24x mais longe do que deveria). Só `width`/`height` continuam
    em unidades de tile nessa mesma linha (o layout escalado so mexeu nos
    centros, unico campo que o calculo de distancia do streaming le) --
    esses dois SIM precisam da conversao aqui."""
    sprite_pool = world.get_pool("sprite")
    transform_pool = world.get_pool("transform")

    def _on_room_activated(room_row: np.void, packed_entity_id: int) -> None:
        index = unpack_index(packed_entity_id)
        width_px = float(room_row["width"]) * TILE_PIXELS
        height_px = float(room_row["height"]) * TILE_PIXELS

        t_row = transform_pool.dense_row_of(index)
        t_view = transform_pool.active_view()
        t_view["position_x"][t_row] = float(room_row["center_x"])  # ja em pixels -- ver docstring
        t_view["position_y"][t_row] = float(room_row["center_y"])  # ja em pixels -- ver docstring
        t_view["rotation_rad"][t_row] = 0.0
        t_view["scale_x"][t_row] = width_px / 8.0
        t_view["scale_y"][t_row] = height_px / 8.0

        s_row = sprite_pool.dense_row_of(index)
        s_view = sprite_pool.active_view()
        s_view["texture_id"][s_row] = SHAPE_RECT
        s_view["tint_r"][s_row] = 40
        s_view["tint_g"][s_row] = 40
        s_view["tint_b"][s_row] = 55
        s_view["tint_a"][s_row] = 255
        s_view["layer_z"][s_row] = 0

    return _on_room_activated


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
    v_view["linear_y"][v_row] = 0.0
    v_view["angular"][v_row] = 0.0

    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = 10.0
    h_view["half_height"][h_row] = 10.0
    h_view["collision_layer"][h_row] = LAYER_PLAYER
    h_view["collision_mask"][h_row] = LAYER_ENEMY

    sprite_pool = world.get_pool("sprite")
    s_row = sprite_pool.dense_row_of(index)
    s_view = sprite_pool.active_view()
    s_view["texture_id"][s_row] = SHAPE_CIRCLE
    s_view["tint_r"][s_row] = 90
    s_view["tint_g"][s_row] = 160
    s_view["tint_b"][s_row] = 255
    s_view["tint_a"][s_row] = 255
    s_view["layer_z"][s_row] = 20

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    hp_row = health_pool.dense_row_of(index)
    hp_view = health_pool.active_view()
    hp_view["entity_kind"][hp_row] = EntityKind.PLAYER
    hp_view["current_hp"][hp_row] = PLAYER_MAX_HP
    hp_view["max_hp"][hp_row] = PLAYER_MAX_HP
    hp_view["contact_damage"][hp_row] = 0.0
    hp_view["destroy_on_hit"][hp_row] = False

    facing_pool = world.get_pool(FACING_POOL_NAME)
    f_row = facing_pool.dense_row_of(index)
    f_view = facing_pool.active_view()
    f_view["facing_x"][f_row] = 0.0
    f_view["facing_y"][f_row] = -1.0

    return index


def _spawn_enemy(world: World, spawn_x: float, spawn_y: float, hp: float, contact_damage: float) -> None:
    packed_entity_id = world.create_entity(ENEMY_ARCHETYPE_NAME)
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
    v_view["linear_y"][v_row] = 0.0
    v_view["angular"][v_row] = 0.0

    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = 8.0
    h_view["half_height"][h_row] = 8.0
    h_view["collision_layer"][h_row] = LAYER_ENEMY
    h_view["collision_mask"][h_row] = LAYER_PLAYER | LAYER_PROJECTILE

    sprite_pool = world.get_pool("sprite")
    s_row = sprite_pool.dense_row_of(index)
    s_view = sprite_pool.active_view()
    s_view["texture_id"][s_row] = SHAPE_CIRCLE
    s_view["tint_r"][s_row] = 90
    s_view["tint_g"][s_row] = 200
    s_view["tint_b"][s_row] = 90
    s_view["tint_a"][s_row] = 255
    s_view["layer_z"][s_row] = 10

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    hp_row = health_pool.dense_row_of(index)
    hp_view = health_pool.active_view()
    hp_view["entity_kind"][hp_row] = EntityKind.ENEMY
    hp_view["current_hp"][hp_row] = hp
    hp_view["max_hp"][hp_row] = hp
    hp_view["contact_damage"][hp_row] = contact_damage
    hp_view["destroy_on_hit"][hp_row] = False


def build_game(config: EngineConfig) -> GameLoop:
    """
    Monta o Jogo Roguelite completo: gera a masmorra PRIMEIRO (puro dado/RNG,
    sem nenhuma dependencia de `World`/`MemoryManager` -- `DungeonGenerator`/
    `StrictRandom` nao tocam ECS), monta um `UniformGrid` dimensionado pelos
    limites reais dela, e SO ENTAO usa `CompositionRoot(config).build(
    spatial_grid=...)` pra montar o `World` generico (Pilar 1/2) ja com
    deteccao de colisao acelerada (ROADMAP M9.1 -- antes rodava forca-bruta
    O(n^2), nada passava uma grade). Registra por cima as pools/arquetipos/
    sistemas especificos deste jogo (Pilar 3 + HUD), spawna jogador/inimigos,
    equipa a arma inicial, liga o streaming real de salas (ROADMAP M9.2 --
    antes eram sprites estaticos sempre presentes), e retorna um `GameLoop`
    pronto para `.run()`.
    """
    strict_random = StrictRandom(root_seed=DUNGEON_ROOT_SEED)
    layout = DungeonGenerator(
        max_rooms=DUNGEON_MAX_ROOMS, room_size_range=DUNGEON_ROOM_SIZE_RANGE
    ).generate(strict_random, level_seed=DUNGEON_LEVEL_SEED)

    spatial_grid = UniformGrid(
        world_bounds=_world_bounds_from_tiles(layout),
        cell_size=GRID_CELL_SIZE,
        entity_capacity=config.entity_capacity,
        max_candidate_pairs=GRID_MAX_CANDIDATE_PAIRS,
    )
    game_loop = CompositionRoot(config).build(spatial_grid=spatial_grid)
    world = game_loop.world

    world.create_pool(HEALTH_POOL_NAME, HEALTH_DTYPE, dense_capacity=config.entity_capacity)
    world.create_pool(FACING_POOL_NAME, FACING_DTYPE, dense_capacity=config.entity_capacity)
    world.create_pool(INVENTORY_POOL_NAME, INVENTORY_SLOT_DTYPE, dense_capacity=4)

    # Carrega data/archetypes/roguelite/*.json de verdade -- so funciona porque as
    # pools especificas acima ja existem neste ponto; ArchetypeLoader valida isso
    # ANTES de registrar qualquer coisa. Subpasta dedicada (nao data/archetypes/
    # direto): o enemy_goblin.json da raiz e escaneado pelos testes genericos do
    # Pilar 3 contra um world sem a pool 'health'.
    ArchetypeLoader(ROGUELITE_ARCHETYPES_DIR).load_and_register_all(world)

    difficulty = DifficultyLoader(DIFFICULTIES_DIR).load(DIFFICULTY_ID)

    spawn_room = layout.rooms[0]
    player_index = _spawn_player(
        world,
        spawn_x=float(spawn_room["center_x"]) * TILE_PIXELS,
        spawn_y=float(spawn_room["center_y"]) * TILE_PIXELS,
    )

    # Streaming real de salas (ROADMAP M9.2): a ancora e o jogador que acabou
    # de nascer -- por isso so pode ser registrado DEPOIS de `_spawn_player`.
    # A sala inicial ativa no proprio primeiro `world.step()` (distancia 0 do
    # centro dela, dentro de ROOM_ACTIVATION_RADIUS), sem tratamento especial.
    world.register_system(
        DungeonStreamingSystem(
            _layout_with_pixel_space_centers(layout),
            ROOM_BACKDROP_ARCHETYPE_NAME,
            ROOM_ACTIVATION_RADIUS,
            ROOM_DEACTIVATION_RADIUS,
            "transform",
            world.pack_current(player_index),
            on_room_activated=_make_on_room_activated(world),
        )
    )

    enemy_health = 30.0 * float(difficulty["enemy_health_multiplier"])
    enemy_contact_damage = 8.0 * float(difficulty["enemy_damage_multiplier"])
    placement_rng = strict_random.stream(RandomStreamPurpose.ENEMY_PLACEMENT)
    for room in layout.rooms[1:]:
        jitter_x = float(placement_rng.uniform(-2.0, 2.0))
        jitter_y = float(placement_rng.uniform(-2.0, 2.0))
        _spawn_enemy(
            world,
            spawn_x=(float(room["center_x"]) + jitter_x) * TILE_PIXELS,
            spawn_y=(float(room["center_y"]) + jitter_y) * TILE_PIXELS,
            hp=enemy_health,
            contact_damage=enemy_contact_damage,
        )

    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = InventoryPool(world.get_pool(INVENTORY_POOL_NAME), max_slots_per_owner=1)
    weapon_loader = WeaponLoader(WEAPONS_DIR)
    weapon_definitions = weapon_loader.load_all_definitions()
    weapon_def_id = stable_id_from_name(STARTER_WEAPON_ID)
    equipped_row = weapon_loader.materialize(
        weapon_def_id, weapon_definitions, inventory, modifier_stack,
        owner_local_index=0, slot_index=0, instance_source_id=1,
    )
    equipped_slot = inventory.active_view()[equipped_row]
    damage_attribute_index = int(equipped_slot["damage_attribute_index"])
    cooldown_attribute_index = int(equipped_slot["cooldown_attribute_index"])
    speed_attribute_index = int(equipped_slot["range_attribute_index"])  # "range" guarda projectile_speed -- ver WeaponLoader

    world.register_system(
        PlayerMovementSystem(game_loop.input_provider, "velocity", FACING_POOL_NAME, player_index, PLAYER_MOVE_SPEED)
    )
    world.register_system(
        EnemyChaseSystem(HEALTH_POOL_NAME, "transform", "velocity", player_index, ENEMY_CHASE_SPEED)
    )
    world.register_system(
        WeaponFireSystem(
            input_provider=game_loop.input_provider,
            transform_pool_name="transform",
            velocity_pool_name="velocity",
            facing_pool_name=FACING_POOL_NAME,
            health_pool_name=HEALTH_POOL_NAME,
            hitbox_pool_name="hitbox",
            sprite_pool_name="sprite",
            player_entity_index=player_index,
            projectile_archetype_name=PROJECTILE_ARCHETYPE_NAME,
            modifier_stack=modifier_stack,
            damage_attribute_index=damage_attribute_index,
            cooldown_attribute_index=cooldown_attribute_index,
            speed_attribute_index=speed_attribute_index,
            projectile_half_extent=PROJECTILE_HALF_EXTENT,
            projectile_collision_layer=LAYER_PROJECTILE,
            projectile_collision_mask=LAYER_ENEMY,
            projectile_texture_id=SHAPE_CIRCLE,
            projectile_tint_rgba=(255, 230, 120, 255),
        )
    )
    world.register_system(ModifierApplicationSystem((modifier_stack,)))

    damage_system = DamageOnCollisionSystem(_find_collision_system(world), HEALTH_POOL_NAME, player_index)
    world.register_system(damage_system)

    base_gameplay_scene = game_loop.current_scene
    assert isinstance(base_gameplay_scene, GameplayScene)
    viewport_size = (config.window_width, config.window_height)

    def _defeat_scene_factory() -> EndScene:
        return EndScene(
            game_loop.input_provider, game_loop, base_gameplay_scene, "VOCE MORREU", viewport_size
        )

    def _victory_scene_factory() -> EndScene:
        return EndScene(
            game_loop.input_provider, game_loop, base_gameplay_scene, "VITORIA!", viewport_size
        )

    world.register_system(
        GameOverOnDeathSystem(game_loop, damage_system, _defeat_scene_factory, _victory_scene_factory)
    )
    world.register_system(QuitOnActionSystem(game_loop.input_provider, game_loop))

    game_loop.set_on_draw_ui(
        build_hud_callback(world, HEALTH_POOL_NAME, player_index, damage_system, viewport_size)
    )

    return game_loop
