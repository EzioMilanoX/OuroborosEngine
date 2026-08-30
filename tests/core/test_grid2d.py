# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa Grid2D: conversao mundo<->celula, leitura em lote com fora-dos-limites, is_solid."""
from __future__ import annotations

import numpy as np

from ouroboros.core.grid2d import Grid2D


def test_world_to_cell_maps_origin_to_cell_zero():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)
    col, row = grid.world_to_cell(np.array([0.0]), np.array([0.0]))
    assert col[0] == 0
    assert row[0] == 0


def test_world_to_cell_respects_cell_boundaries():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)
    col, row = grid.world_to_cell(np.array([31.999, 32.0]), np.array([0.0, 0.0]))
    assert list(col) == [0, 1]
    assert row[0] == 0 and row[1] == 0


def test_world_to_cell_applies_origin_offset():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0, origin_x=100.0, origin_y=200.0)
    col, row = grid.world_to_cell(np.array([100.0]), np.array([200.0]))
    assert col[0] == 0
    assert row[0] == 0


def test_batch_get_reads_populated_cell_value():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)
    grid.cells[2, 1] = 5  # row=2, col=1

    value = grid.batch_get(np.array([1]), np.array([2]))

    assert value[0] == 5


def test_batch_get_out_of_bounds_returns_the_sentinel_without_indexing_the_real_array():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)

    value = grid.batch_get(np.array([-1, 100]), np.array([-1, 100]), out_of_bounds_value=9)

    assert list(value) == [9, 9]


def test_batch_get_defaults_out_of_bounds_to_solid():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)

    value = grid.batch_get(np.array([-1]), np.array([0]))

    assert value[0] == 1


def test_is_solid_reflects_nonzero_cell_values():
    grid = Grid2D(cols=4, rows=4, cell_size=32.0)
    grid.cells[0, 2] = 1  # row=0, col=2 -> world x in [64,96), y in [0,32)

    assert bool(grid.is_solid(np.array([70.0]), np.array([10.0]))[0]) is True
    assert bool(grid.is_solid(np.array([10.0]), np.array([10.0]))[0]) is False


def test_cells_shape_is_rows_by_cols():
    grid = Grid2D(cols=5, rows=3, cell_size=16.0)
    assert grid.cells.shape == (3, 5)
    assert grid.cols == 5
    assert grid.rows == 3
