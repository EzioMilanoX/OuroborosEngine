"""
Testa `games.platformer.composition.build_game` de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
confirma que o vertical slice builda corretamente e roda alguns frames
reais sem crashar, mesmo padrao de
tests/games/test_roguelite_composition_headless.py.
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem

from games.platformer.composition import CELL_SIZE, MOVE_SPEED, build_game

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "platformer" / "config.json"


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


def _player_position(game_loop: GameLoop):
    transform_pool = game_loop.world.get_pool("transform")
    view = transform_pool.active_view()
    return float(view["position_x"][0]), float(view["position_y"][0])


def _player_entity_index(game_loop: GameLoop) -> int:
    """Descobre o entity_index (GLOBAL, nao a linha densa 0 usada por
    `_player_position` acima) do jogador via a pool `hitbox` -- o unico tipo
    de entidade neste jogo que a possui (os backdrops de tile so tem
    transform+sprite) -- mesmo espirito de como os testes do Roguelite
    inferem estado via pools, nao um indice hardcoded. `TileCollisionSystem.
    is_grounded()` e indexado por entity_index GLOBAL (administrado pelo
    free-list do MemoryManager, que desempilha do topo -- NUNCA
    necessariamente 0), ao contrario da linha densa (que comeca em 0 pro
    primeiro spawn e por isso `_player_position` pode indexar direto)."""
    hitbox_pool = game_loop.world.get_pool("hitbox")
    return int(hitbox_pool.active_entity_indices()[0])


def test_build_game_registers_the_tile_collision_and_gravity_systems(game_loop: GameLoop):
    kinds = [type(system).__name__ for system in game_loop.world.systems]
    assert "TileCollisionSystem" in kinds
    assert "GravitySystem" in kinds
    assert kinds.index("PhysicsSystem") < kinds.index("TileCollisionSystem") < kinds.index("GravitySystem")


def test_build_game_spawns_the_player_and_the_solid_tile_backdrops(game_loop: GameLoop):
    sprite_pool = game_loop.world.get_pool("sprite")
    # 1 jogador + 25 celulas solidas do nivel ASCII hardcoded (5 da plataforma + 20 do chao)
    assert sprite_pool.count == 26


def test_game_runs_several_real_frames_without_crashing(game_loop: GameLoop, bind_quit_after):
    poll_count = bind_quit_after(game_loop.input_provider, quit_after=5)

    game_loop.run()

    assert poll_count["n"] == 5


def test_player_settles_onto_the_floor_from_spawn(game_loop: GameLoop):
    for _ in range(30):
        game_loop.world.step(1.0 / 60.0)

    tile_system = next(s for s in game_loop.world.systems if isinstance(s, TileCollisionSystem))
    assert tile_system.is_grounded(_player_entity_index(game_loop)) is True


def test_holding_move_right_moves_the_player_right(game_loop: GameLoop):
    for _ in range(10):
        game_loop.world.step(1.0 / 60.0)  # deixa assentar primeiro
    start_x, _y = _player_position(game_loop)

    game_loop.input_provider.is_action_held = lambda action_name: action_name == "move_right"
    for _ in range(30):
        game_loop.world.step(1.0 / 60.0)

    end_x, _y = _player_position(game_loop)
    assert end_x > start_x
    assert end_x - start_x == pytest.approx(MOVE_SPEED * 0.5, rel=0.1)


def test_holding_move_left_moves_the_player_left(game_loop: GameLoop):
    for _ in range(10):
        game_loop.world.step(1.0 / 60.0)
    start_x, _y = _player_position(game_loop)

    game_loop.input_provider.is_action_held = lambda action_name: action_name == "move_left"
    for _ in range(30):
        game_loop.world.step(1.0 / 60.0)

    end_x, _y = _player_position(game_loop)
    assert end_x < start_x


def test_jumping_while_grounded_moves_the_player_upward(game_loop: GameLoop):
    for _ in range(10):
        game_loop.world.step(1.0 / 60.0)
    _x, floor_y = _player_position(game_loop)

    game_loop.input_provider.is_action_pressed = lambda action_name: action_name == "jump"
    game_loop.world.step(1.0 / 60.0)
    game_loop.input_provider.is_action_pressed = lambda action_name: False
    for _ in range(5):
        game_loop.world.step(1.0 / 60.0)

    _x, y_after_jump = _player_position(game_loop)
    assert y_after_jump < floor_y  # +y = baixo -- pular sobe, y diminui


def test_jumping_while_airborne_does_not_apply_a_second_impulse(game_loop: GameLoop):
    """PlayerJumpSystem checa is_grounded() -- pular no meio do ar (dupla-pulo)
    fica fora de escopo do M12, jamais deve acontecer."""
    for _ in range(10):
        game_loop.world.step(1.0 / 60.0)

    velocity_pool = game_loop.world.get_pool("velocity")

    game_loop.input_provider.is_action_pressed = lambda action_name: action_name == "jump"
    game_loop.world.step(1.0 / 60.0)
    velocity_after_first_jump = float(velocity_pool.active_view()["linear_y"][0])
    assert velocity_after_first_jump < 0.0  # subindo

    # ainda no ar, pressiona "jump" nesse mesmo frame de novo -- nao deve reforcar o impulso
    game_loop.world.step(1.0 / 60.0)
    velocity_after_second_press = float(velocity_pool.active_view()["linear_y"][0])
    # a velocidade so deve ter mudado pela gravidade normal desde o 1o pulo, nunca
    # sido resetada de volta pro impulso completo de novo
    assert velocity_after_second_press > velocity_after_first_jump


def test_quit_action_stops_the_game_loop(game_loop: GameLoop):
    game_loop.input_provider.is_action_pressed = lambda action_name: action_name == "quit"
    game_loop.input_provider.wants_quit = lambda: False

    game_loop.run()  # deve retornar (game_loop.stop() chamado de dentro do proprio QuitOnActionSystem)
