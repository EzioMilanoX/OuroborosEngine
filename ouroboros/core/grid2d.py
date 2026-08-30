# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Grade 2D generica (ROADMAP M12): container puro de dados, sem World/ECS."""
from __future__ import annotations

from typing import Tuple

import numpy as np


class Grid2D:
    """
    Grade 2D densa, tipada, com conversao mundo<->celula -- sem NENHUMA
    semantica de "solido"/pathfinding embutida (isso e responsabilidade de
    quem consome a grade, ex.: `TileCollisionSystem`). Mesma filosofia de
    `ParticleStorage` (Pilar 1-adjacente, mas sem acoplamento a `World`):
    um container de dados puro que um `ISystem` opera por cima.

    `cells` e indexado `[row, col]` (convencao NumPy padrao, linha primeiro)
    -- `world_to_cell`/todo o resto desta classe SEMPRE retorna/aceita
    `(col, row)`, nessa ordem, pra nao inverter X/Y silenciosamente; ler
    `cells` diretamente exige lembrar da inversao.

    Deliberadamente NAO reusa `ouroboros.roguelite.generation.schemas`
    (`TILE_DTYPE`/`TileType`) -- aquilo e especifico de masmorra procedural
    (salas/corredores); esta classe e agnostica de genero. Cuidado: os
    valores de `TileType` (`FLOOR=1`, etc.) satisfariam `!= 0` se alguem um
    dia tentasse reusar `TILE_DTYPE.tile_type` direto como conteudo de
    celula aqui -- isso classificaria FLOOR como solido por engano. Nunca
    fazer essa ponte sem traduzir os valores explicitamente.
    """

    def __init__(
        self,
        cols: int,
        rows: int,
        cell_size: float,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        dtype: np.dtype = np.uint8,
    ) -> None:
        """Pre-aloca `cells` com shape `(rows, cols)`, zerada -- o chamador
        popula o conteudo (ex.: parseando um nivel ASCII) escrevendo direto
        em `self.cells[row, col] = valor`."""
        self._cols = cols
        self._rows = rows
        self._cell_size = float(cell_size)
        self._origin_x = origin_x
        self._origin_y = origin_y
        self._cells = np.zeros((rows, cols), dtype=dtype)

    @property
    def cells(self) -> np.ndarray:
        """View (sem copia) do array denso `[row, col]` -- popular direto."""
        return self._cells

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cell_size(self) -> float:
        return self._cell_size

    @property
    def origin_x(self) -> float:
        return self._origin_x

    @property
    def origin_y(self) -> float:
        return self._origin_y

    def world_to_cell(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Converte posicoes em espaco de mundo pra indices de celula
        `(col, row)` -- vetorizado, aceita tanto arrays NumPy quanto
        escalares Python (promovidos automaticamente pelas operacoes
        abaixo). Indices fora da grade saem negativos ou `>= cols/rows`
        (nao sao clampados aqui -- ver `batch_get`)."""
        col = np.floor((np.asarray(x) - self._origin_x) / self._cell_size).astype(np.int64)
        row = np.floor((np.asarray(y) - self._origin_y) / self._cell_size).astype(np.int64)
        return col, row

    def batch_get(self, col: np.ndarray, row: np.ndarray, out_of_bounds_value: int = 1) -> np.ndarray:
        """Le `cells[row, col]` pra cada par, retornando `out_of_bounds_value`
        (default 1 -- fora da grade conta como solido, pra nunca deixar uma
        entidade cair pra fora do nivel) onde o indice estiver fora dos
        limites, sem nunca indexar o array real fora dos limites (usa
        `np.clip` internamente so pro lookup, descartado onde `out_of_bounds`)."""
        col = np.asarray(col)
        row = np.asarray(row)
        in_bounds = (col >= 0) & (col < self._cols) & (row >= 0) & (row < self._rows)
        safe_col = np.clip(col, 0, self._cols - 1)
        safe_row = np.clip(row, 0, self._rows - 1)
        return np.where(in_bounds, self._cells[safe_row, safe_col], out_of_bounds_value)

    def is_solid(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Conveniencia: `batch_get(*world_to_cell(x, y)) != 0` -- o unico
        contrato de "solido" que esta classe define (qualquer valor de
        celula diferente de zero). `TileCollisionSystem` usa isso
        diretamente; um consumidor futuro com terrenos mais ricos
        (rampas, plataformas de mao unica) precisaria de uma checagem
        propria, nao desta conveniencia v1."""
        col, row = self.world_to_cell(x, y)
        return self.batch_get(col, row) != 0
