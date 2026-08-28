"""Composicao do Jogo Roguelite: registra pools/arquetipos/sistemas especificos por cima do CompositionRoot generico."""
from __future__ import annotations

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
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT
from ouroboros.roguelite.combat.schemas import EntityKind, HEALTH_DTYPE
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader
from ouroboros.roguelite.generation.dungeon_generator import DungeonGenerator
from ouroboros.roguelite.generation.random import RandomStreamPurpose, StrictRandom
from ouroboros.roguelite.items.inventory_pool import InventoryPool
from ouroboros.roguelite.items.schemas import INVENTORY_SLOT_DTYPE
from ouroboros.roguelite.items.weapon_loader import WeaponLoader
from ouroboros.roguelite.loaders.difficulty_loader import DifficultyLoader
from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack
from ouroboros.roguelite.systems.damage_system import DamageOnCollisionSystem
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


def _spawn_room_backdrops(world: World, rooms: np.ndarray) -> None:
    """Representacao visual ESTATICA (sempre presente, nunca destruida) de cada
    sala: um retangulo grande posicionado/escalado a partir de `DungeonLayout.rooms`.
    Sem geometria por tile nem colisao de parede -- limitacao de v1 documentada."""
    sprite_pool = world.get_pool("sprite")
    transform_pool = world.get_pool("transform")
    for room in rooms:
        packed_entity_id = world.create_entity(ROOM_BACKDROP_ARCHETYPE_NAME)
        index = unpack_index(packed_entity_id)

        width_px = float(room["width"]) * TILE_PIXELS
        height_px = float(room["height"]) * TILE_PIXELS
        t_row = transform_pool.dense_row_of(index)
        t_view = transform_pool.active_view()
        t_view["position_x"][t_row] = float(room["center_x"]) * TILE_PIXELS
        t_view["position_y"][t_row] = float(room["center_y"]) * TILE_PIXELS
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
    Monta o Jogo Roguelite completo: usa `CompositionRoot(config).build()`
    para o `World` generico (Pilar 1/2), registra por cima as pools/
    arquetipos/sistemas especificos deste jogo (Pilar 3 + HUD), gera a
    masmorra, spawna jogador/inimigos, equipa a arma inicial, e retorna
    um `GameLoop` pronto para `.run()`.
    """
    game_loop = CompositionRoot(config).build()
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

    strict_random = StrictRandom(root_seed=DUNGEON_ROOT_SEED)
    layout = DungeonGenerator(
        max_rooms=DUNGEON_MAX_ROOMS, room_size_range=DUNGEON_ROOM_SIZE_RANGE
    ).generate(strict_random, level_seed=DUNGEON_LEVEL_SEED)
    _spawn_room_backdrops(world, layout.rooms)

    spawn_room = layout.rooms[0]
    player_index = _spawn_player(
        world,
        spawn_x=float(spawn_room["center_x"]) * TILE_PIXELS,
        spawn_y=float(spawn_room["center_y"]) * TILE_PIXELS,
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
