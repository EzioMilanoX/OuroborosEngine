# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa BattlefieldGrid: terreno estatico, is_passable, reconstrucao de ocupacao."""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.tactics.grid.battlefield_grid import BattlefieldGrid
from ouroboros.tactics.grid.schemas import TerrainType


def test_all_cells_start_walkable_with_default_move_cost():
    grid = BattlefieldGrid(cols=4, rows=4)
    assert grid.terrain_type_at(1, 1) == TerrainType.WALKABLE
    assert grid.move_cost_at(1, 1) == 1.0


def test_set_cell_rejects_move_cost_below_one():
    grid = BattlefieldGrid(cols=4, rows=4)
    with pytest.raises(ValueError):
        grid.set_cell(1, 1, TerrainType.DIFFICULT, move_cost=0.5)


def test_set_cell_updates_terrain_and_move_cost():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.set_cell(2, 2, TerrainType.DIFFICULT, move_cost=2.0)

    assert grid.terrain_type_at(2, 2) == TerrainType.DIFFICULT
    assert grid.move_cost_at(2, 2) == 2.0
    assert grid.is_blocked_terrain(2, 2) is False


def test_is_blocked_terrain_reflects_blocked_cells():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.set_cell(0, 0, TerrainType.BLOCKED)
    assert grid.is_blocked_terrain(0, 0) is True


def test_is_passable_false_out_of_bounds():
    grid = BattlefieldGrid(cols=4, rows=4)
    assert grid.is_passable(-1, 0) is False
    assert grid.is_passable(0, -1) is False
    assert grid.is_passable(4, 0) is False
    assert grid.is_passable(0, 4) is False


def test_is_passable_false_on_blocked_terrain():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.set_cell(1, 1, TerrainType.BLOCKED)
    assert grid.is_passable(1, 1) is False


def test_is_passable_false_when_occupied_by_someone_else():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.rebuild_occupancy(np.array([7]), np.array([1]), np.array([1]))
    assert grid.is_passable(1, 1) is False
    assert grid.is_passable(1, 1, ignoring_entity_index=7) is True


def test_occupant_at_reports_minus_one_when_empty():
    grid = BattlefieldGrid(cols=4, rows=4)
    assert grid.occupant_at(0, 0) == -1


def test_rebuild_occupancy_replaces_the_whole_map_not_a_patch():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.rebuild_occupancy(np.array([1, 2]), np.array([0, 1]), np.array([0, 1]))
    assert grid.occupant_at(0, 0) == 1
    assert grid.occupant_at(1, 1) == 2

    # segunda reconstrucao com um roster DIFERENTE -- a unidade 1 morreu/saiu
    grid.rebuild_occupancy(np.array([2]), np.array([2]), np.array([2]))
    assert grid.occupant_at(0, 0) == -1  # nao deve sobrar residuo da chamada anterior
    assert grid.occupant_at(1, 1) == -1
    assert grid.occupant_at(2, 2) == 2


def test_rebuild_occupancy_with_no_entities_clears_the_map():
    grid = BattlefieldGrid(cols=4, rows=4)
    grid.rebuild_occupancy(np.array([1]), np.array([0]), np.array([0]))
    grid.rebuild_occupancy(np.array([], dtype=np.int64), np.array([], dtype=np.int64), np.array([], dtype=np.int64))
    assert grid.occupant_at(0, 0) == -1
