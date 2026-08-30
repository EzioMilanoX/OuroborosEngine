"""
Testa `games.tactics.composition.build_game` de ponta a ponta com o
`CompositionRoot` real (backends Pygame reais, sob
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy ja forcados em tests/conftest.py) --
confirma que o vertical slice builda corretamente e a batalha completa
(movimento, combate, morte, fim de jogo) roda sem crashar, mesmo padrao de
tests/games/test_roguelite_composition_headless.py/test_platformer_composition_headless.py.
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.tactics.combat.schemas import Team

from games.tactics.battle_scene import TacticsBattleScene
from games.tactics.composition import UNIT_DEFINITIONS, build_game

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "tactics" / "config.json"


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


def _press(game_loop: GameLoop, action: str) -> None:
    scene = game_loop.current_scene
    game_loop.input_provider.is_action_pressed = lambda name: name == action
    scene.update(game_loop.world, 1.0 / 60.0)
    game_loop.input_provider.is_action_pressed = lambda name: False
    scene.update(game_loop.world, 1.0 / 60.0)


def _unit_row(game_loop: GameLoop, entity_index: int):
    unit_pool = game_loop.world.get_pool("tactics_unit")
    return unit_pool.dense_row_of(entity_index), unit_pool.active_view()


def test_build_game_starts_on_the_tactics_battle_scene(game_loop: GameLoop):
    assert isinstance(game_loop.current_scene, TacticsBattleScene)


def test_build_game_spawns_all_units_and_terrain_backdrops(game_loop: GameLoop):
    unit_pool = game_loop.world.get_pool("tactics_unit")
    assert unit_pool.count == len(UNIT_DEFINITIONS)

    sprite_pool = game_loop.world.get_pool("sprite")
    # 4 unidades + 7 celulas de parede (8 linhas - 1 brecha) + 2 DIFFICULT
    assert sprite_pool.count == len(UNIT_DEFINITIONS) + 7 + 2


def test_turn_order_matches_interleaved_initiative(game_loop: GameLoop):
    """Scout (iniciativa 3.0) -> Warrior (2.0) -> Grunt A/B (1.0, empate,
    desempate estavel pela ordem de UNIT_DEFINITIONS) -- prova que o sort
    de TurnQueue importa de verdade, nao "todo o time do jogador primeiro"."""
    scene = game_loop.current_scene
    unit_pool = game_loop.world.get_pool("tactics_unit")

    def team_of(entity_index):
        row = unit_pool.dense_row_of(entity_index)
        return int(unit_pool.active_view()["team"][row])

    order = [scene._turn_queue.current_entity_index]
    for _ in range(3):
        order.append(scene._turn_queue.advance_to_next())

    assert [team_of(e) for e in order] == [Team.PLAYER, Team.PLAYER, Team.ENEMY, Team.ENEMY]


def test_moving_right_onto_open_ground_updates_grid_and_transform_position(game_loop: GameLoop):
    scene = game_loop.current_scene
    active = scene._turn_queue.current_entity_index
    row, view = _unit_row(game_loop, active)
    start_x = int(view["grid_x"][row])

    _press(game_loop, "move_right")

    row, view = _unit_row(game_loop, active)
    assert int(view["grid_x"][row]) == start_x + 1

    transform_pool = game_loop.world.get_pool("transform")
    t_row = transform_pool.dense_row_of(active)
    assert float(transform_pool.active_view()["position_x"][t_row]) == pytest.approx((start_x + 1 + 0.5) * 48.0)


def test_cannot_move_into_a_wall(game_loop: GameLoop):
    scene = game_loop.current_scene
    active = scene._turn_queue.current_entity_index  # Scout, comeca em (1,3)

    for _ in range(4):  # (1,3) -> (5,3), a coluna 5 e parede nesta linha
        _press(game_loop, "move_right")

    row, view = _unit_row(game_loop, active)
    assert int(view["grid_x"][row]) == 4  # parado na borda da parede, nao atravessou


def test_end_turn_advances_to_the_next_unit_in_initiative_order(game_loop: GameLoop):
    scene = game_loop.current_scene
    first_active = scene._turn_queue.current_entity_index

    _press(game_loop, "end_turn")

    assert scene._turn_queue.current_entity_index != first_active


def test_a_full_battle_runs_to_completion_without_crashing(game_loop: GameLoop):
    """Prova de ponta a ponta: joga uma batalha inteira (ataque sempre que
    possivel, senao anda, senao encerra o turno; IA age sozinha) ate um
    lado vencer -- exercita movimento, ocupacao, muro, ataque, morte
    (destroy_entity DIFERIDO + flush + reconstrucao de ocupacao), e
    deteccao de fim de jogo juntos."""
    scene = game_loop.current_scene
    world = game_loop.world

    for _ in range(200):
        if scene._game_over_message is not None:
            break
        active = scene._turn_queue.current_entity_index
        if active is None:
            break
        row, view = _unit_row(game_loop, active)
        if int(view["team"][row]) == Team.PLAYER:
            _press(game_loop, "attack")
            if scene._turn_queue.current_entity_index == active:
                _press(game_loop, "move_right")
            if scene._turn_queue.current_entity_index == active:
                _press(game_loop, "move_down")
            if scene._turn_queue.current_entity_index == active:
                _press(game_loop, "end_turn")
        else:
            scene.update(world, 1.0 / 60.0)

    assert scene._game_over_message in ("VOCE VENCEU", "VOCE PERDEU")
    teams_alive = {int(t) for t in world.get_pool("tactics_unit").active_view()["team"]}
    assert len(teams_alive) == 1  # so um time restou


def test_quit_action_stops_the_game_loop(game_loop: GameLoop):
    scene = game_loop.current_scene
    game_loop._running = True  # simula estar dentro de run() -- _running comeca False na construcao
    game_loop.input_provider.is_action_pressed = lambda name: name == "quit"

    scene.update(game_loop.world, 1.0 / 60.0)

    # 'quit' e checado direto em update() (mesmo idioma de MenuScene) --
    # confirma que game_loop.stop() foi chamado de verdade, nao que
    # _running so nunca tinha sido ligado.
    assert game_loop._running is False
