"""Schemas SoA para o layout de dungeon procedural. Especificos do Roguelite -- nao entram em COMPONENT_SCHEMAS."""
from __future__ import annotations

import numpy as np


class TileType:
    """Codigos inteiros de tipo de tile, armazenaveis em `int8`.

    Constantes de classe simples (nao `enum.Enum`): um membro de
    `IntEnum` ja e um `int` e se atribui a um campo NumPy `int8` com o
    mesmo custo de uma constante simples -- a escolha aqui e so por
    minimalismo de dependencia, nao por evitar boxing/conversao (que nao
    existiria de qualquer forma com `IntEnum`).
    """

    EMPTY: int = 0
    FLOOR: int = 1
    WALL: int = 2
    DOOR: int = 3
    HAZARD: int = 4


ROOM_DTYPE: np.dtype = np.dtype(
    [
        ("room_id", np.int32),
        ("grid_x", np.int32),
        ("grid_y", np.int32),
        ("width", np.int32),
        ("height", np.int32),
        ("room_type", np.int16),
        ("tile_offset", np.int32),
        ("tile_count", np.int32),
        ("center_x", np.float32),
        ("center_y", np.float32),
    ]
)
"""Schema SoA de uma sala do dungeon.

Campos:
    room_id: identificador estavel da sala dentro do dungeon gerado; e
        tambem o ORDINAL (indice de linha) usado por
        `DungeonStreamingSystem` para indexar sua `ComponentPool` de
        controle de instanciacao -- portanto e permanente e nunca
        reciclado apos a geracao.
    grid_x, grid_y, width, height: geometria da sala na grade macro.
    room_type: indice para uma tabela de tipos de sala definida em JSON
        (nunca hardcoded em Python).
    tile_offset, tile_count: fatia desta sala dentro do array global de
        tiles (`TILE_DTYPE`), evitando realocar por sala.
    center_x, center_y: centro da sala no espaco de mundo, usado por
        `DungeonStreamingSystem` para calculo vetorizado de distancia
        sem reler `width`/`height`/`grid_x`/`grid_y` a cada frame.
"""

TILE_DTYPE: np.dtype = np.dtype(
    [
        ("room_id", np.int32),
        ("local_x", np.int16),
        ("local_y", np.int16),
        ("tile_type", np.int8),
    ]
)
"""Schema SoA de um tile individual, relativo a sala dona (`room_id`)."""
