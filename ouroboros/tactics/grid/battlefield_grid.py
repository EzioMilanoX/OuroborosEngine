# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Grade discreta do campo de batalha: terreno estatico + ocupacao reconstruivel (ROADMAP M13)."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ouroboros.tactics.grid.schemas import TACTICS_CELL_DTYPE, TerrainType


class BattlefieldGrid:
    """
    Grade 2D discreta e pequena (tipicamente ~10x8) de uma batalha tatica --
    NAO reusa `ouroboros.core.grid2d.Grid2D` (essa e pro Platformer: uma
    grade CONTINUAMENTE testada todo frame pra colisao AABB; esta e
    consultada por EVENTO discreto -- um pedido de movimento/pathfinding --
    nunca por frame. As semanticas divergem demais pra convergir sem
    indirecao artificial: nenhuma das duas conhece a outra).

    Duas colecoes com ciclos de vida DIFERENTES, mesmo espirito de
    `ModifierStack` (atributos permanentes vs. entradas reciclaveis):
      - `_cells` (terreno): estatico, populado uma unica vez no setup da
        batalha via `set_cell`, nunca muda depois.
      - `_occupant_entity_index`: RECONSTRUIDO POR INTEIRO a cada chamada
        de `rebuild_occupancy` (mesmo idioma de `UniformGrid.rebuild` --
        nunca um patch incremental por movimento, pra nunca vazar uma
        entrada obsoleta de uma unidade morta/movida). Deve ser chamado
        DEPOIS de `World.flush()` sempre que uma unidade morrer (destroy_entity
        e DIFERIDO -- ver docstring de `World.destroy_entity` -- reconstruir
        antes do flush veria a unidade morta como ocupante ainda).
    """

    def __init__(self, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows
        self._cells = np.zeros(cols * rows, dtype=TACTICS_CELL_DTYPE)
        # np.zeros deixaria move_cost em 0.0 -- violaria a invariante "todo custo
        # de aresta >= 1.0" (ver set_cell) pra toda celula nunca tocada por
        # set_cell, quebrando a admissibilidade da heuristica de Manhattan em
        # find_path silenciosamente. WALKABLE (terrain_type=0, ja o default de
        # np.zeros) com move_cost=1.0 e o estado inicial correto.
        self._cells["move_cost"] = 1.0
        self._occupant_entity_index = np.full(cols * rows, -1, dtype=np.int64)

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self._cols and 0 <= y < self._rows

    def to_index(self, x: int, y: int) -> int:
        return y * self._cols + x

    def set_cell(self, x: int, y: int, terrain_type: int, move_cost: float = 1.0) -> None:
        """Popula UMA celula de terreno -- so no setup da batalha (nunca
        depois que unidades comecam a se mover). Levanta `ValueError` se
        `move_cost < 1.0`: a heuristica de Manhattan de `pathfinding.find_path`
        so e admissivel (nunca superestima o custo real restante) se todo
        custo de aresta for >= 1.0 -- um "terreno rapido" hipotetico
        quebraria isso silenciosamente (A* devolveria um caminho subotimo
        sem levantar erro nenhum)."""
        if move_cost < 1.0:
            raise ValueError(f"move_cost deve ser >= 1.0 (heuristica de Manhattan exige isso), recebido {move_cost}")
        row = self._cells[self.to_index(x, y)]
        row["terrain_type"] = terrain_type
        row["move_cost"] = move_cost

    def terrain_type_at(self, x: int, y: int) -> int:
        return int(self._cells[self.to_index(x, y)]["terrain_type"])

    def move_cost_at(self, x: int, y: int) -> float:
        return float(self._cells[self.to_index(x, y)]["move_cost"])

    def is_blocked_terrain(self, x: int, y: int) -> bool:
        return self.terrain_type_at(x, y) == TerrainType.BLOCKED

    def occupant_at(self, x: int, y: int) -> int:
        """Retorna o `entity_index` do ocupante em `(x, y)`, ou `-1` se vazia."""
        return int(self._occupant_entity_index[self.to_index(x, y)])

    def is_passable(self, x: int, y: int, ignoring_entity_index: Optional[int] = None) -> bool:
        """Dentro dos limites, terreno nao-`BLOCKED`, e (vazia OU ocupada
        exatamente por `ignoring_entity_index` -- pra permitir que uma
        unidade calcule caminho/alcance a partir da PROPRIA celula, que ela
        mesma ocupa). NAO faz excecao especial pra nenhuma outra celula --
        o chamador (`find_path`/`reachable_cells`) e quem decide tratar sua
        celula de partida como sempre passavel, independente disso (ver
        docstring de `find_path`)."""
        if not self.in_bounds(x, y):
            return False
        if self.is_blocked_terrain(x, y):
            return False
        occupant = self.occupant_at(x, y)
        return occupant == -1 or occupant == ignoring_entity_index

    def rebuild_occupancy(self, entity_indices: np.ndarray, grid_x: np.ndarray, grid_y: np.ndarray) -> None:
        """Reconstroi `_occupant_entity_index` DO ZERO a partir do roster
        completo e ATUAL de unidades vivas (mesmo idioma de
        `UniformGrid.rebuild` -- nunca um patch incremental). Chamar
        DEPOIS de `World.flush()` toda vez que uma unidade morrer (ver
        docstring de classe) -- caso contrario a unidade morta, ainda
        presente na pool ate o flush, continuaria ocupando sua ultima
        celula pra sempre."""
        self._occupant_entity_index[:] = -1
        if entity_indices.size == 0:
            return
        cell_indices = grid_y.astype(np.int64) * self._cols + grid_x.astype(np.int64)
        self._occupant_entity_index[cell_indices] = entity_indices
