# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa CompositionRoot.build() com o backend Pygame real, headless (SDL dummy drivers)."""
import json

import pygame
import pytest

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.core.systems.spatial_grid import UniformGrid
from ouroboros.core.world import World


@pytest.fixture
def engine_config(tmp_path):
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(json.dumps({"fire": "KEY_SPACE"}), encoding="utf-8")
    difficulty_path = tmp_path / "normal.json"
    difficulty_path.write_text(json.dumps({"name": "normal"}), encoding="utf-8")

    return EngineConfig(
        window_width=320,
        window_height=240,
        window_title="OuroborosEngine test",
        entity_capacity=256,
        difficulty_path=str(difficulty_path),
        input_bindings_path=str(bindings_path),
    )


def _find_collision_system(game_loop) -> CollisionSystem:
    for system in game_loop.world.systems:
        if isinstance(system, CollisionSystem):
            return system
    raise AssertionError("CompositionRoot.build() deveria ter registrado um CollisionSystem")


def test_composition_root_builds_a_working_game_loop(engine_config):
    root = CompositionRoot(engine_config)
    game_loop = root.build()

    assert isinstance(game_loop, GameLoop)
    assert isinstance(game_loop.world, World)
    assert game_loop.world.get_pool("transform") is not None
    assert game_loop.renderer.get_viewport_size() == (320, 240)

    game_loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def test_composition_root_defaults_to_brute_force_collision_when_no_grid_is_given(engine_config):
    """Regressao de retrocompatibilidade: omitir `spatial_grid` continua
    dando o mesmo CollisionSystem forca-bruta de sempre."""
    game_loop = CompositionRoot(engine_config).build()

    assert _find_collision_system(game_loop)._spatial_grid is None

    game_loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def test_composition_root_forwards_a_supplied_spatial_grid_to_collision_system(engine_config):
    grid = UniformGrid(world_bounds=(0.0, 0.0, 100.0, 100.0), cell_size=10.0,
                       entity_capacity=64, max_candidate_pairs=64)

    game_loop = CompositionRoot(engine_config).build(spatial_grid=grid)

    assert _find_collision_system(game_loop)._spatial_grid is grid

    game_loop.renderer.shutdown()
    if pygame.mixer.get_init():
        pygame.mixer.quit()


def test_engine_config_from_json_round_trips(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "window_width": 800,
                "window_height": 600,
                "window_title": "Ouroboros",
                "entity_capacity": 4096,
                "difficulty_path": "data/difficulties/normal.json",
                "input_bindings_path": "data/input_bindings/default_keyboard.json",
            }
        ),
        encoding="utf-8",
    )

    config = EngineConfig.from_json(str(config_path))

    assert config.window_width == 800
    assert config.entity_capacity == 4096
