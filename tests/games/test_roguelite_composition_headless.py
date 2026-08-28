"""
Testa `games.roguelite.composition.build_game` de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
mesmo padrao de tests/games/test_rhythm_game_composition_headless.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene
from ouroboros.interfaces.renderer import SHAPE_RECT
from ouroboros.roguelite.combat.schemas import EntityKind
from ouroboros.roguelite.generation.dungeon_generator import DungeonGenerator
from ouroboros.roguelite.generation.random import StrictRandom
from ouroboros.roguelite.loaders.difficulty_loader import DifficultyLoader
from ouroboros.roguelite.loaders.room_type_loader import RoomTypeLoader

from games.roguelite.composition import (
    DIFFICULTIES_DIR,
    DIFFICULTY_ID,
    DUNGEON_LEVEL_SEED,
    DUNGEON_MAX_ROOMS,
    DUNGEON_ROOM_SIZE_RANGE,
    DUNGEON_ROOT_SEED,
    ENEMY_ARCHETYPE_NAME,
    FACING_POOL_NAME,
    HEALTH_POOL_NAME,
    PLAYER_ARCHETYPE_NAME,
    PROJECTILE_ARCHETYPE_NAME,
    ROOM_BACKDROP_ARCHETYPE_NAME,
    ROOM_TYPES_PATH,
    build_game,
)
from games.roguelite.end_scene import EndScene

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "roguelite" / "config.json"


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig.from_json(str(_CONFIG_PATH))


@pytest.fixture
def game_loop(config: EngineConfig) -> GameLoop:
    loop = build_game(config)
    yield loop
    loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def _player_entity_index(game_loop: GameLoop) -> int:
    """Descobre o entity_index do jogador via o discriminador entity_kind na pool de
    HP -- nao depende de build_game expor o indice diretamente (mesmo espirito de
    como os testes do Jogo Musical inferem estado via pools, nao referencias diretas)."""
    health_pool = game_loop.world.get_pool(HEALTH_POOL_NAME)
    view = health_pool.active_view()
    mask = view["entity_kind"] == EntityKind.PLAYER
    assert mask.sum() == 1
    return int(health_pool.active_entity_indices()[mask][0])


def test_build_game_registers_product_specific_pools_and_archetypes(game_loop: GameLoop):
    world = game_loop.world
    assert world.has_pool(HEALTH_POOL_NAME)
    assert world.has_pool(FACING_POOL_NAME)
    assert world.has_archetype(PLAYER_ARCHETYPE_NAME)
    assert world.has_archetype(ENEMY_ARCHETYPE_NAME)
    assert world.has_archetype(PROJECTILE_ARCHETYPE_NAME)
    assert world.has_archetype(ROOM_BACKDROP_ARCHETYPE_NAME)


def test_build_game_spawns_exactly_one_player_and_some_enemies(game_loop: GameLoop):
    health_pool = game_loop.world.get_pool(HEALTH_POOL_NAME)
    view = health_pool.active_view()
    assert int(np.count_nonzero(view["entity_kind"] == EntityKind.PLAYER)) == 1
    assert int(np.count_nonzero(view["entity_kind"] == EntityKind.ENEMY)) > 0


def test_game_runs_several_real_frames_without_crashing(game_loop: GameLoop, bind_quit_after):
    poll_count = bind_quit_after(game_loop.input_provider, quit_after=5)

    game_loop.run()

    assert poll_count["n"] == 5


def test_player_moves_when_holding_a_direction(game_loop: GameLoop, bind_quit_after):
    player_index = _player_entity_index(game_loop)
    transform_pool = game_loop.world.get_pool("transform")
    row = transform_pool.dense_row_of(player_index)
    start_x = float(transform_pool.active_view()["position_x"][row])

    game_loop.input_provider.is_action_held = lambda action_name: action_name == "move_right"
    bind_quit_after(game_loop.input_provider, quit_after=10)

    game_loop.run()

    end_x = float(transform_pool.active_view()["position_x"][transform_pool.dense_row_of(player_index)])
    assert end_x > start_x


def test_camera_follows_the_player(game_loop: GameLoop, bind_quit_after):
    player_index = _player_entity_index(game_loop)
    transform_pool = game_loop.world.get_pool("transform")

    game_loop.input_provider.is_action_held = lambda action_name: action_name == "move_right"
    bind_quit_after(game_loop.input_provider, quit_after=10)
    game_loop.run()

    row = transform_pool.dense_row_of(player_index)
    player_x = float(transform_pool.active_view()["position_x"][row])
    player_y = float(transform_pool.active_view()["position_y"][row])
    viewport_width, viewport_height = game_loop.renderer.get_viewport_size()

    assert game_loop.renderer._cam_dx == pytest.approx(viewport_width / 2.0 - player_x)
    assert game_loop.renderer._cam_dy == pytest.approx(viewport_height / 2.0 - player_y)


def test_firing_spawns_a_projectile(game_loop: GameLoop):
    health_pool = game_loop.world.get_pool(HEALTH_POOL_NAME)
    projectiles_before = int(np.count_nonzero(health_pool.active_view()["entity_kind"] == EntityKind.PROJECTILE))

    game_loop.input_provider.is_action_pressed = lambda action_name: action_name == "fire"
    game_loop.world.step(0.016)

    projectiles_after = int(np.count_nonzero(health_pool.active_view()["entity_kind"] == EntityKind.PROJECTILE))
    assert projectiles_after == projectiles_before + 1


def test_player_death_pushes_end_scene_and_esc_quits_from_it(game_loop: GameLoop):
    """Prova de ponta a ponta do achado 2 do plano: EndScene precisa checar 'quit'
    diretamente, ja que QuitOnActionSystem fica congelado assim que ela e empilhada."""
    world = game_loop.world
    player_index = _player_entity_index(game_loop)
    health_pool = world.get_pool(HEALTH_POOL_NAME)
    transform_pool = world.get_pool("transform")

    # Forca uma morte imediata: zera o hp do jogador e cria um inimigo bem em cima dele
    # pra garantir colisao (nao dependemos de esperar a perseguicao real por muitos frames).
    hp_row = health_pool.dense_row_of(player_index)
    health_pool.active_view()["current_hp"][hp_row] = 1.0
    player_row = transform_pool.dense_row_of(player_index)
    player_x = float(transform_pool.active_view()["position_x"][player_row])
    player_y = float(transform_pool.active_view()["position_y"][player_row])

    from ouroboros.core.memory.handles import unpack_index
    packed_enemy = world.create_entity("enemy_goblin")
    enemy_index = unpack_index(packed_enemy)
    t_row = transform_pool.dense_row_of(enemy_index)
    transform_pool.active_view()["position_x"][t_row] = player_x
    transform_pool.active_view()["position_y"][t_row] = player_y
    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(enemy_index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = 8.0
    h_view["half_height"][h_row] = 8.0
    h_view["collision_layer"][h_row] = 2
    h_view["collision_mask"][h_row] = 1 | 4
    hp2_row = health_pool.dense_row_of(enemy_index)
    hp2_view = health_pool.active_view()
    hp2_view["entity_kind"][hp2_row] = EntityKind.ENEMY
    hp2_view["current_hp"][hp2_row] = 30.0
    hp2_view["max_hp"][hp2_row] = 30.0
    hp2_view["contact_damage"][hp2_row] = 999.0
    hp2_view["destroy_on_hit"][hp2_row] = False

    world.step(0.016)

    assert isinstance(game_loop.current_scene, EndScene)

    game_loop.input_provider.is_action_pressed = lambda action_name: action_name == "quit"
    game_loop.input_provider.wants_quit = lambda: False
    game_loop.run()  # deve retornar (game_loop.stop() chamado de dentro do proprio update() da EndScene)

    assert isinstance(game_loop.current_scene, EndScene)  # nunca deu pop -- so parou o loop


def test_room_backdrop_tint_matches_its_room_type_from_room_types_json(game_loop: GameLoop):
    """ROADMAP M10.1: prova de ponta a ponta que `room_row["room_type"]"]`
    (existente desde a geracao original da masmorra, nunca lido antes)
    realmente determina o tint da entidade de fundo -- regenera o MESMO
    layout deterministico (mesma seed que `build_game` usa) so pra saber o
    room_type esperado da sala 0 (spawn do jogador, ativa desde o 1o frame),
    sem reconstruir nenhum World."""
    layout = DungeonGenerator(
        max_rooms=DUNGEON_MAX_ROOMS, room_size_range=DUNGEON_ROOM_SIZE_RANGE
    ).generate(StrictRandom(root_seed=DUNGEON_ROOT_SEED), level_seed=DUNGEON_LEVEL_SEED)
    room_type_tints = RoomTypeLoader(ROOM_TYPES_PATH).load()
    expected_tint = room_type_tints[int(layout.rooms[0]["room_type"])]

    # A sala 0 so materializa (DungeonStreamingSystem) durante um world.step()
    # -- build_game() sozinho ainda nao rodou nenhum frame.
    game_loop.world.step(0.016)

    sprite_pool = game_loop.world.get_pool("sprite")
    view = sprite_pool.active_view()
    backdrop_rows = np.nonzero(view["texture_id"] == SHAPE_RECT)[0]
    assert len(backdrop_rows) >= 1
    row = backdrop_rows[0]
    actual_tint = (
        int(view["tint_r"][row]), int(view["tint_g"][row]), int(view["tint_b"][row]), int(view["tint_a"][row]),
    )
    assert actual_tint == expected_tint


def test_enemies_per_room_follows_spawn_rate_multiplier(game_loop: GameLoop):
    """ROADMAP M10.3: spawn_rate_multiplier era lido do JSON mas nunca
    consumido -- "normal" (multiplier=1.0) deve continuar gerando
    exatamente 1 inimigo por sala (comportamento de sempre, antes do M10)."""
    difficulty = DifficultyLoader(DIFFICULTIES_DIR).load(DIFFICULTY_ID)
    assert float(difficulty["spawn_rate_multiplier"]) == pytest.approx(1.0)

    layout = DungeonGenerator(
        max_rooms=DUNGEON_MAX_ROOMS, room_size_range=DUNGEON_ROOM_SIZE_RANGE
    ).generate(StrictRandom(root_seed=DUNGEON_ROOT_SEED), level_seed=DUNGEON_LEVEL_SEED)
    expected_enemy_count = len(layout.rooms) - 1  # todas as salas exceto a de spawn (rooms[0])

    health_pool = game_loop.world.get_pool(HEALTH_POOL_NAME)
    actual_enemy_count = int(np.count_nonzero(health_pool.active_view()["entity_kind"] == EntityKind.ENEMY))
    assert actual_enemy_count == expected_enemy_count
