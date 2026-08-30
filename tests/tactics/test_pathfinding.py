# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa find_path/reachable_cells/has_line_of_sight sobre uma BattlefieldGrid real."""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.tactics.grid.battlefield_grid import BattlefieldGrid
from ouroboros.tactics.grid.pathfinding import find_path, has_line_of_sight, reachable_cells
from ouroboros.tactics.grid.schemas import TerrainType


def _empty_grid(cols=6, rows=6) -> BattlefieldGrid:
    return BattlefieldGrid(cols=cols, rows=rows)


# ------------------------------------------------------------ find_path


def test_find_path_straight_line_on_open_ground():
    grid = _empty_grid()
    path = find_path(grid, (0, 0), (3, 0))
    assert path == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_find_path_returns_single_cell_when_start_equals_goal():
    grid = _empty_grid()
    assert find_path(grid, (2, 2), (2, 2)) == [(2, 2)]


def test_find_path_routes_around_a_wall():
    grid = _empty_grid()
    for y in range(0, 4):
        grid.set_cell(2, y, TerrainType.BLOCKED)

    path = find_path(grid, (0, 0), (4, 0))

    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (4, 0)
    assert all(not grid.is_blocked_terrain(x, y) for x, y in path)


def test_find_path_returns_none_when_fully_walled_off():
    grid = _empty_grid()
    for y in range(grid.rows):
        grid.set_cell(2, y, TerrainType.BLOCKED)

    assert find_path(grid, (0, 0), (4, 0)) is None


def test_find_path_treats_start_as_passable_even_without_ignoring_entity_index():
    """Achado da critica: um chamador que avalie o caminho de OUTRA unidade
    (sem passar ignoring_entity_index) nao pode ser barrado so por a
    origem estar ocupada pela propria unidade que esta nela."""
    grid = _empty_grid()
    grid.rebuild_occupancy(np.array([99]), np.array([0]), np.array([0]))

    path = find_path(grid, (0, 0), (2, 0))  # sem ignoring_entity_index

    assert path == [(0, 0), (1, 0), (2, 0)]


def test_find_path_returns_none_when_goal_is_occupied_by_someone_else():
    """Achado da critica: goal NAO recebe tratamento especial -- uma celula
    ocupada por outra unidade e corretamente inalcancavel."""
    grid = _empty_grid()
    grid.rebuild_occupancy(np.array([42]), np.array([3]), np.array([0]))

    assert find_path(grid, (0, 0), (3, 0)) is None


def test_find_path_prefers_cheaper_route_over_difficult_terrain():
    grid = _empty_grid()
    grid.set_cell(1, 0, TerrainType.DIFFICULT, move_cost=5.0)

    path = find_path(grid, (0, 0), (2, 0))

    # rota alternativa por baixo (custo 1 cada) e mais barata que atravessar
    # a celula dificil (custo 5) -- A* deve escolher o desvio.
    assert (1, 0) not in path


def test_find_path_raises_when_start_out_of_bounds():
    grid = _empty_grid()
    with pytest.raises(ValueError):
        find_path(grid, (-1, 0), (0, 0))


def test_find_path_raises_when_goal_out_of_bounds():
    grid = _empty_grid()
    with pytest.raises(ValueError):
        find_path(grid, (0, 0), (99, 0))


# ------------------------------------------------------------ reachable_cells


def test_reachable_cells_includes_start_at_zero_cost():
    grid = _empty_grid()
    reachable = reachable_cells(grid, (2, 2), move_budget=0.0)
    assert reachable == {(2, 2): 0.0}


def test_reachable_cells_respects_the_budget():
    grid = _empty_grid()
    reachable = reachable_cells(grid, (0, 0), move_budget=2.0)

    assert (2, 0) in reachable
    assert (3, 0) not in reachable  # custaria 3, alem do orcamento


def test_reachable_cells_respects_float_tolerance_at_the_exact_budget_boundary():
    """Achado da critica: 3 celulas de custo 1.1 (float32, nao exatamente
    representavel) somadas devem continuar alcancaveis com orcamento
    exatamente 3.3, sem a soma acumulada (com deriva de ponto flutuante)
    ficar uma fracao de ULP acima e rejeitar a celula por engano."""
    grid = _empty_grid(cols=5, rows=1)
    for x in range(1, 4):
        grid.set_cell(x, 0, TerrainType.DIFFICULT, move_cost=1.1)

    reachable = reachable_cells(grid, (0, 0), move_budget=3.3)

    assert (3, 0) in reachable


def test_reachable_cells_does_not_cross_blocked_terrain():
    grid = _empty_grid(cols=6, rows=1)  # grade 1D -- sem como contornar o bloqueio
    grid.set_cell(1, 0, TerrainType.BLOCKED)

    reachable = reachable_cells(grid, (0, 0), move_budget=10.0)

    assert (1, 0) not in reachable
    assert (2, 0) not in reachable  # so alcancavel atravessando a celula bloqueada


def test_reachable_cells_treats_start_as_passable_even_when_occupied():
    grid = _empty_grid()
    grid.rebuild_occupancy(np.array([1]), np.array([0]), np.array([0]))

    reachable = reachable_cells(grid, (0, 0), move_budget=1.0)

    assert (0, 0) in reachable


# ------------------------------------------------------------ has_line_of_sight


def test_los_clear_on_open_ground():
    grid = _empty_grid()
    assert has_line_of_sight(grid, (0, 0), (4, 0)) is True


def test_los_blocked_by_a_wall_in_between():
    grid = _empty_grid()
    grid.set_cell(2, 0, TerrainType.BLOCKED)
    assert has_line_of_sight(grid, (0, 0), (4, 0)) is False


def test_los_always_clear_between_adjacent_cells_even_if_target_is_blocked():
    grid = _empty_grid()
    grid.set_cell(1, 0, TerrainType.BLOCKED)  # o proprio alvo -- nunca testado por oclusao
    assert has_line_of_sight(grid, (0, 0), (1, 0)) is True


def test_los_diagonal_passes_through_a_single_blocked_corner():
    """So UMA das duas celulas ortogonais adjacentes ao passo diagonal esta
    bloqueada -- a linha ainda consegue "espremer" pela quina aberta."""
    grid = _empty_grid()
    grid.set_cell(1, 0, TerrainType.BLOCKED)  # so um dos dois cantos
    assert has_line_of_sight(grid, (0, 0), (2, 2)) is True


def test_los_diagonal_blocked_when_both_corners_are_walls():
    """Achado da critica: regra explicita de canto -- uma diagonal nao pode
    espremer entre duas paredes que se tocam so na quina. Usa (0,0)->(2,2)
    (nao (0,0)->(1,1)): um alvo diagonal a distancia 1 nunca acrestesta o
    passo intermediario -- o loop chega e para ANTES de checar o canto
    (celula de destino nunca e testada por oclusao). So a partir de
    distancia 2 existe um passo diagonal REALMENTE intermediario pra
    testar."""
    grid = _empty_grid()
    grid.set_cell(1, 0, TerrainType.BLOCKED)
    grid.set_cell(0, 1, TerrainType.BLOCKED)
    assert has_line_of_sight(grid, (0, 0), (2, 2)) is False


def test_los_ignores_occupancy_only_terrain_blocks():
    grid = _empty_grid()
    grid.rebuild_occupancy(np.array([1]), np.array([2]), np.array([0]))
    assert has_line_of_sight(grid, (0, 0), (4, 0)) is True


def test_los_from_a_cell_to_itself_is_always_true():
    grid = _empty_grid()
    assert has_line_of_sight(grid, (2, 2), (2, 2)) is True
