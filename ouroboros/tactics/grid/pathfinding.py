# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Funcoes puras de pathfinding sobre uma BattlefieldGrid (ROADMAP M13) -- FORA do hot-path (por evento discreto, nao por frame)."""
from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple

from ouroboros.tactics.grid.battlefield_grid import BattlefieldGrid

Cell = Tuple[int, int]

_NEIGHBOR_OFFSETS: Tuple[Cell, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""So ortogonal (4 direcoes) -- sem diagonal, decisao de escopo do v1
(ver ROADMAP M13, "fora de escopo: movimento diagonal")."""

_BUDGET_TOLERANCE = 1e-6
"""Tolerancia de ponto flutuante pra comparar custo acumulado (float32 nas
celulas, promovido a float64 no acumulo Python) contra um orcamento/custo
ja conhecido -- sem isso, um valor como 1.1 (nao exatamente representavel
em float32) acumulado por varios passos poderia ficar uma fracao de ULP
acima do esperado e rejeitar uma celula que deveria ser exatamente
alcancavel (mesma classe de bug que o epsilon de fronteira do M12)."""


def _manhattan_distance(a: Cell, b: Cell) -> float:
    return float(abs(a[0] - b[0]) + abs(a[1] - b[1]))


def _reconstruct_path(came_from: Dict[Cell, Cell], current: Cell) -> List[Cell]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def find_path(
    grid: BattlefieldGrid,
    start: Cell,
    goal: Cell,
    ignoring_entity_index: Optional[int] = None,
) -> Optional[List[Cell]]:
    """A* ortogonal (4 direcoes) sobre `grid`; custo de aresta = `move_cost`
    da celula de DESTINO (heuristica de Manhattan e admissivel porque
    `BattlefieldGrid.set_cell` garante `move_cost >= 1.0` em toda celula).

    `start` e SEMPRE tratado como passavel, independente de
    `ignoring_entity_index`/`BattlefieldGrid.is_passable` -- e a propria
    celula que a unidade que pediu o caminho ja ocupa; um chamador que
    avalie o caminho de OUTRA unidade sem passar `ignoring_entity_index`
    (ex.: "essa aliada consegue chegar ali?") nao pode ser barrado so por a
    origem estar "ocupada" pela propria unidade que esta nela.

    `goal` NAO recebe nenhum tratamento especial -- se estiver ocupado por
    outra unidade, e CORRETAMENTE inalcancavel (retorna `None`); um
    chamador que queira "chegar perto de" uma celula ocupada (ex.: uma IA
    mirando a unidade inimiga mais proxima) deve escolher uma celula vizinha
    livre como `goal`, nao a celula ocupada em si.

    Levanta `ValueError` se `start`/`goal` estiverem fora dos limites da
    grade. Retorna o caminho (lista de celulas, INCLUINDO `start` e
    `goal`) ou `None` se nao houver caminho.
    """
    if not grid.in_bounds(*start):
        raise ValueError(f"start fora dos limites da grade: {start}")
    if not grid.in_bounds(*goal):
        raise ValueError(f"goal fora dos limites da grade: {goal}")
    if start == goal:
        return [start]

    counter = 0
    open_heap: List[Tuple[float, int, Cell]] = [(_manhattan_distance(start, goal), counter, start)]
    g_score: Dict[Cell, float] = {start: 0.0}
    came_from: Dict[Cell, Cell] = {}
    closed: set = set()

    while open_heap:
        _f_score, _tie, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct_path(came_from, current)
        closed.add(current)

        for dx, dy in _NEIGHBOR_OFFSETS:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor != start and not grid.is_passable(neighbor[0], neighbor[1], ignoring_entity_index):
                continue
            tentative_g = g_score[current] + grid.move_cost_at(neighbor[0], neighbor[1])
            if neighbor in g_score and tentative_g >= g_score[neighbor] - _BUDGET_TOLERANCE:
                continue
            g_score[neighbor] = tentative_g
            came_from[neighbor] = current
            counter += 1
            heapq.heappush(open_heap, (tentative_g + _manhattan_distance(neighbor, goal), counter, neighbor))

    return None


def reachable_cells(
    grid: BattlefieldGrid,
    start: Cell,
    move_budget: float,
    ignoring_entity_index: Optional[int] = None,
) -> Dict[Cell, float]:
    """Dijkstra com orcamento de custo (BFS simples subestimaria terreno
    `DIFFICULT`, que custa mais de 1.0 por celula) -- retorna toda celula
    alcancavel a partir de `start` com custo acumulado `<= move_budget`
    (com `_BUDGET_TOLERANCE`), mapeada pro custo total gasto pra chegar
    la. Inclui `start` a custo `0.0`. Mesma excecao de `start` sempre
    passavel de `find_path` (ver sua docstring). Levanta `ValueError` se
    `start` estiver fora dos limites."""
    if not grid.in_bounds(*start):
        raise ValueError(f"start fora dos limites da grade: {start}")

    costs: Dict[Cell, float] = {start: 0.0}
    counter = 0
    open_heap: List[Tuple[float, int, Cell]] = [(0.0, counter, start)]
    visited: set = set()

    while open_heap:
        cost, _tie, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        for dx, dy in _NEIGHBOR_OFFSETS:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor != start and not grid.is_passable(neighbor[0], neighbor[1], ignoring_entity_index):
                continue
            tentative_cost = cost + grid.move_cost_at(neighbor[0], neighbor[1])
            if tentative_cost > move_budget + _BUDGET_TOLERANCE:
                continue
            if neighbor in costs and tentative_cost >= costs[neighbor] - _BUDGET_TOLERANCE:
                continue
            costs[neighbor] = tentative_cost
            counter += 1
            heapq.heappush(open_heap, (tentative_cost, counter, neighbor))

    return costs


def _is_blocked_transparent_out_of_bounds(grid: BattlefieldGrid, x: int, y: int) -> bool:
    """Celula fora dos limites conta como TRANSPARENTE (nao bloqueia) pra
    checagem de canto de `has_line_of_sight` -- nao ha parede nenhuma la,
    so o fim do mapa."""
    return grid.in_bounds(x, y) and grid.is_blocked_terrain(x, y)


def has_line_of_sight(grid: BattlefieldGrid, from_xy: Cell, to_xy: Cell) -> bool:
    """Caminha a linha de Bresenham entre os CENTROS das celulas `from_xy`
    e `to_xy` -- os dois extremos nunca sao testados por oclusao (so as
    celulas INTERMEDIARIAS importam: uma unidade sempre "ve" a propria
    celula e a celula do alvo, mesmo que o alvo esteja em terreno
    `BLOCKED`). Terreno `BLOCKED` numa celula intermediaria bloqueia;
    `DIFFICULT` nao. Ocupacao (unidades) NUNCA bloqueia linha de visao, so
    terreno.

    Regra explicita de canto (bug classico de Bresenham): um passo
    DIAGONAL (x e y mudam ao mesmo tempo) e bloqueado se AMBAS as celulas
    ortogonais adjacentes aquele passo forem `BLOCKED` -- uma linha nao
    pode "espremer" pela quina entre duas paredes que se tocam so na
    diagonal. Inofensivo pro unico uso atual (ataque corpo-a-corpo, sempre
    a distancia ortogonal 1 -- uma linha reta sem nenhum passo diagonal),
    mas esta funcao e escrita como utilitario geral pra um consumidor
    futuro (alcance/visao a distancia)."""
    x0, y0 = from_xy
    x1, y1 = to_xy

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    step_x_dir = 1 if x1 > x0 else -1
    step_y_dir = 1 if y1 > y0 else -1
    err = dx - dy

    x, y = x0, y0
    while (x, y) != (x1, y1):
        prev_x, prev_y = x, y
        doubled_err = 2 * err
        moves_x = doubled_err > -dy
        moves_y = doubled_err < dx
        if moves_x:
            err -= dy
            x += step_x_dir
        if moves_y:
            err += dx
            y += step_y_dir

        if (x, y) == (x1, y1):
            break  # celula de destino nunca e testada por oclusao

        if moves_x and moves_y:
            corner_a_blocked = _is_blocked_transparent_out_of_bounds(grid, prev_x + step_x_dir, prev_y)
            corner_b_blocked = _is_blocked_transparent_out_of_bounds(grid, prev_x, prev_y + step_y_dir)
            if corner_a_blocked and corner_b_blocked:
                return False

        if grid.is_blocked_terrain(x, y):
            return False

    return True
