# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gera um DungeonLayout reprodutivel a partir de uma seed, via StrictRandom."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from ouroboros.roguelite.generation.random import RandomStreamPurpose, StrictRandom
from ouroboros.roguelite.generation.schemas import ROOM_DTYPE, TILE_DTYPE, TileType

# Quantidade de valores distintos de `ROOM_DTYPE.room_type` que este gerador
# produz (ver `_carve_rooms`). Consumido por `RoomTypeLoader` para validar
# que `data/room_types.json` cobre todo o intervalo gerado.
ROOM_TYPE_COUNT = 4


def _rectangles_overlap(
    x: int, y: int, width: int, height: int, placed_rects: List[Tuple[int, int, int, int]], margin: int
) -> bool:
    """Testa AABB de `(x, y, width, height)` (com uma folga `margin`) contra
    todos os retangulos ja aceitos em `placed_rects`."""
    for other_x, other_y, other_width, other_height in placed_rects:
        if (
            x < other_x + other_width + margin
            and x + width + margin > other_x
            and y < other_y + other_height + margin
            and y + height + margin > other_y
        ):
            return True
    return False


@dataclass(frozen=True)
class DungeonLayout:
    """Resultado imutavel e serializavel de uma geracao de dungeon.

    Produzido inteiramente FORA do loop de gameplay (durante carregamento/
    transicao de nivel); pode ser construido alocando objetos Python
    livremente -- nao e hot-path.

    Atributos:
        rooms: array `ROOM_DTYPE` com `room_count` linhas validas.
        tiles: array `TILE_DTYPE` com `tile_count` linhas validas,
            indexado por `rooms['tile_offset'] .. +rooms['tile_count']`.
        seed: seed raiz que originou este layout (replay/debug/telemetria).
        algorithm_version: versao do algoritmo de geracao usada, para
            detectar incompatibilidade ao tentar reproduzir um layout
            salvo com uma versao antiga do gerador.
    """

    rooms: np.ndarray
    tiles: np.ndarray
    seed: int
    algorithm_version: int


class DungeonGenerator:
    """Constroi um `DungeonLayout` reprodutivel a partir de uma seed.

    Invariante de reprodutibilidade: `generate(level_seed)` chamado duas
    vezes com a MESMA `StrictRandom.root_seed` e o MESMO `level_seed`
    produz arrays `rooms`/`tiles` byte-a-byte identicos, desde que
    `ALGORITHM_VERSION` nao tenha mudado entre as chamadas. Toda a
    aleatoriedade vem exclusivamente de
    `strict_random.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=level_seed)`
    -- nenhuma outra fonte de entropia (relogio, `random` global, hash de
    objeto, ordem de iteracao de `dict`/`set` nao deterministica) pode
    influenciar o resultado. Particionar por `salt=level_seed` (em vez de
    reutilizar o mesmo stream para todos os niveis) garante que gerar o
    nivel 7 isoladamente produza o mesmo resultado que gera-lo depois de ja
    ter gerado os niveis 1-6.

    Roda inteiramente fora do loop de gameplay quente; PODE alocar objetos
    Python livremente durante `generate()`.
    """

    ALGORITHM_VERSION: int = 1

    def __init__(self, max_rooms: int, room_size_range: Tuple[int, int]) -> None:
        """Configura limites estruturais da geracao (nao afetam a
        reprodutibilidade do resultado para uma mesma seed + mesma
        configuracao).
        """
        self._max_rooms = int(max_rooms)
        self._room_size_range = (int(room_size_range[0]), int(room_size_range[1]))
        _min_size, max_size = self._room_size_range
        # Grade macro deliberadamente generosa: mantem o custo esperado das
        # tentativas de posicionamento sem sobreposicao baixo (ver
        # `_carve_rooms`), sem exigir um parametro extra de "tamanho de
        # grade" -- deriva-se inteiramente de `max_rooms`/`room_size_range`.
        self._grid_size = max(max_size * 4, self._max_rooms * (max_size + 2) * 2, 16)

    def generate(self, strict_random: StrictRandom, level_seed: int) -> DungeonLayout:
        """Gera um `DungeonLayout` completo e deterministico.

        Consome exclusivamente
        `strict_random.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=level_seed)`
        para todas as decisoes de layout (posicao/tamanho/conexao de
        salas, preenchimento de tiles).
        """
        rng = strict_random.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=level_seed)
        rooms = self._carve_rooms(rng)
        tiles = self._carve_tiles(rooms, rng)
        return DungeonLayout(
            rooms=rooms,
            tiles=tiles,
            seed=strict_random.root_seed,
            algorithm_version=self.ALGORITHM_VERSION,
        )

    def _carve_rooms(self, rng: np.random.Generator) -> np.ndarray:
        """Passo interno: decide posicoes/tamanhos das salas, retorna
        array com dtype `ROOM_DTYPE` (sem `tile_offset`/`tile_count`
        ainda resolvidos).
        """
        rooms = np.zeros(self._max_rooms, dtype=ROOM_DTYPE)
        min_size, max_size = self._room_size_range
        placed_rects: List[Tuple[int, int, int, int]] = []
        margin = 1
        max_attempts = 200
        spacing = max_size + 2
        columns = max(1, int(np.ceil(np.sqrt(self._max_rooms))))

        for room_id in range(self._max_rooms):
            width = int(rng.integers(min_size, max_size + 1))
            height = int(rng.integers(min_size, max_size + 1))
            max_x = max(0, self._grid_size - width)
            max_y = max(0, self._grid_size - height)

            x = y = 0
            placed = False
            for _attempt in range(max_attempts):
                x = int(rng.integers(0, max_x + 1))
                y = int(rng.integers(0, max_y + 1))
                if not _rectangles_overlap(x, y, width, height, placed_rects, margin):
                    placed = True
                    break

            if not placed:
                # Posicionamento de contingencia deterministico (grade
                # regular sem sobreposicao) -- garante terminacao mesmo em
                # configuracoes patologicas (grade pequena/muitas salas),
                # sem comprometer a reprodutibilidade (a sequencia de
                # tentativas ja consumidas do `rng` continua deterministica).
                column = room_id % columns
                row = room_id // columns
                x = column * spacing
                y = row * spacing

            placed_rects.append((x, y, width, height))
            room_type = int(rng.integers(0, ROOM_TYPE_COUNT))
            center_x = x + width / 2.0
            center_y = y + height / 2.0
            rooms[room_id] = (room_id, x, y, width, height, room_type, 0, 0, center_x, center_y)

        return rooms

    def _carve_tiles(self, rooms: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Passo interno: preenche os tiles de cada sala e conecta
        corredores; retorna array `TILE_DTYPE` e atualiza, in-place,
        `tile_offset`/`tile_count` em `rooms`.
        """
        del rng  # Preenchimento de tiles e corredores e inteiramente geometrico/deterministico.
        tile_entries: List[Tuple[int, int, int, int]] = []

        for room_index in range(rooms.shape[0]):
            room = rooms[room_index]
            room_id = int(room["room_id"])
            width = int(room["width"])
            height = int(room["height"])
            offset = len(tile_entries)

            for local_y in range(height):
                for local_x in range(width):
                    is_border = local_x in (0, width - 1) or local_y in (0, height - 1)
                    tile_type = TileType.WALL if is_border else TileType.FLOOR
                    tile_entries.append((room_id, local_x, local_y, tile_type))

            if room_index > 0:
                tile_entries.extend(self._carve_corridor(rooms[room_index - 1], room))

            rooms[room_index]["tile_offset"] = offset
            rooms[room_index]["tile_count"] = len(tile_entries) - offset

        if tile_entries:
            return np.array(tile_entries, dtype=TILE_DTYPE)
        return np.zeros(0, dtype=TILE_DTYPE)

    @staticmethod
    def _carve_corridor(from_room: np.void, to_room: np.void) -> List[Tuple[int, int, int, int]]:
        """Corredor reto em "L" (segmento horizontal + segmento vertical)
        ligando o centro de `from_room` ao centro de `to_room`, expresso
        como tiles `FLOOR` pertencentes a `to_room` (coordenadas locais
        relativas ao `grid_x`/`grid_y` de `to_room`)."""
        start_x = int(round(float(from_room["center_x"])))
        start_y = int(round(float(from_room["center_y"])))
        end_x = int(round(float(to_room["center_x"])))
        end_y = int(round(float(to_room["center_y"])))
        room_id = int(to_room["room_id"])
        grid_x = int(to_room["grid_x"])
        grid_y = int(to_room["grid_y"])

        entries: List[Tuple[int, int, int, int]] = []
        step_x = 1 if end_x >= start_x else -1
        for world_x in range(start_x, end_x + step_x, step_x):
            entries.append((room_id, world_x - grid_x, start_y - grid_y, TileType.FLOOR))
        step_y = 1 if end_y >= start_y else -1
        for world_y in range(start_y, end_y + step_y, step_y):
            entries.append((room_id, end_x - grid_x, world_y - grid_y, TileType.FLOOR))
        return entries
