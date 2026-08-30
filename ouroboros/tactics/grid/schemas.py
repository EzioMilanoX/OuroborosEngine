# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Schema SoA de uma celula do campo de batalha (ROADMAP M13)."""
from __future__ import annotations

from enum import IntEnum

import numpy as np


class TerrainType(IntEnum):
    """Codigos de terreno, armazenaveis em `int8`. Contrato estavel (mesmo
    criterio de `ModifierOperation`/`RandomStreamPurpose`) -- nunca renumerar."""

    WALKABLE = 0
    BLOCKED = 1
    DIFFICULT = 2  # passavel, mas com move_cost > 1.0


TACTICS_CELL_DTYPE: np.dtype = np.dtype(
    [
        ("terrain_type", np.int8),
        ("move_cost", np.float32),
    ]
)
"""Schema de UMA celula do campo de batalha.

Campos:
    terrain_type: um dos valores de `TerrainType`.
    move_cost: custo de movimento pra ENTRAR nesta celula (usado como custo
        de aresta por `pathfinding.find_path`/`reachable_cells` -- sempre
        >= 1.0, ver `BattlefieldGrid.set_cell`, pra manter a heuristica de
        Manhattan admissivel). Irrelevante quando `terrain_type == BLOCKED`
        (a celula nunca e uma aresta valida de qualquer forma).
"""
