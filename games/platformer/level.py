# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Nivel ASCII hardcoded do vertical slice (ROADMAP M12) -- parseado pra uma Grid2D real."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from ouroboros.core.grid2d import Grid2D

SOLID_CHAR = "#"
SPAWN_CHAR = "P"
EMPTY_CHAR = "."

# Chao continuo com um degrau levantado no meio -- o bastante pra exercitar
# corrida (chao plano) e pulo (subir no degrau) sem inimigos/pontuacao
# (fora de escopo do M12). Formato data-driven (JSON) deferido -- 1 nivel
# hardcoded nao justifica um pipeline ainda (ver ROADMAP M12).
LEVEL_ROWS: Tuple[str, ...] = (
    "....................",
    "....................",
    "....................",
    "....................",
    "......#####.........",
    "....................",
    "....................",
    "P...................",
    "####################",
    "....................",
)


class LevelDefinitionError(Exception):
    """Levantado quando o nivel ASCII esta malformado ou o ponto de spawn
    cai dentro de uma celula solida -- falha alto e cedo, na composicao,
    nunca como uma entidade renderizada silenciosamente dentro de uma
    parede (mesmo criterio de todo outro loader data-driven desta engine)."""


@dataclass(frozen=True)
class Level:
    """Resultado do parsing de um nivel ASCII: a `Grid2D` pronta pra
    `CompositionRoot.build(tile_grid=...)`, o ponto de spawn do jogador
    (centro da celula marcada `P`, ja validado como nao-solido), e os
    centros de mundo de cada celula solida (pra spawnar o backdrop
    visual -- so apresentacao, a colisao de verdade e contra `grid`)."""

    grid: Grid2D
    spawn_x: float
    spawn_y: float
    solid_cell_centers: Tuple[Tuple[float, float], ...]


def load_level(cell_size: float = 32.0) -> Level:
    """Parseia `LEVEL_ROWS` pra uma `Level`. Levanta `LevelDefinitionError`
    se as linhas tiverem comprimentos diferentes, se houver mais de um (ou
    nenhum) ponto de spawn, se um caractere desconhecido aparecer, ou se o
    ponto de spawn cair dentro de uma celula solida (validado contra a
    `Grid2D` real ja construida, nao por inspecao textual do ASCII)."""
    rows = LEVEL_ROWS
    row_count = len(rows)
    col_count = len(rows[0])
    for row in rows:
        if len(row) != col_count:
            raise LevelDefinitionError("todas as linhas do nivel ASCII devem ter o mesmo comprimento")

    grid = Grid2D(cols=col_count, rows=row_count, cell_size=cell_size)
    spawn_col = None
    spawn_row = None
    solid_cell_centers: List[Tuple[float, float]] = []

    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char == SOLID_CHAR:
                grid.cells[row_index, col_index] = 1
                solid_cell_centers.append(((col_index + 0.5) * cell_size, (row_index + 0.5) * cell_size))
            elif char == SPAWN_CHAR:
                if spawn_col is not None:
                    raise LevelDefinitionError("nivel ASCII tem mais de um ponto de spawn ('P')")
                spawn_col, spawn_row = col_index, row_index
            elif char != EMPTY_CHAR:
                raise LevelDefinitionError(f"caractere de nivel desconhecido: {char!r}")

    if spawn_col is None:
        raise LevelDefinitionError("nivel ASCII sem ponto de spawn ('P')")

    spawn_x = (spawn_col + 0.5) * cell_size
    spawn_y = (spawn_row + 0.5) * cell_size

    if bool(grid.is_solid([spawn_x], [spawn_y])[0]):
        raise LevelDefinitionError(f"ponto de spawn ({spawn_x}, {spawn_y}) cai dentro de uma celula solida")

    return Level(grid=grid, spawn_x=spawn_x, spawn_y=spawn_y, solid_cell_centers=tuple(solid_cell_centers))
