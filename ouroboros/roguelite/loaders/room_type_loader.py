# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le data/room_types.json e expoe a tabela de tint por room_type como dados puros."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from ouroboros.roguelite.generation.dungeon_generator import ROOM_TYPE_COUNT

RoomTypeTintRGBA = Tuple[int, int, int, int]


class RoomTypeDefinitionError(Exception):
    """Levantado quando `data/room_types.json` nao existe, esta malformado,
    ou nao cobre todo o intervalo de `room_type` que `DungeonGenerator`
    realmente gera (ver `ROOM_TYPE_COUNT`).
    """


class RoomTypeLoader:
    """Le `data/room_types.json` (uma tabela indexada por `ROOM_DTYPE.room_type`,
    nunca hardcoded em Python -- ver docstring do campo) e expoe o tint RGBA
    de cada tipo de sala como dados puros.

    Roda fora do loop de gameplay (montagem do nivel).
    """

    def __init__(self, room_types_path: Path) -> None:
        """Aponta para o arquivo `data/room_types.json`."""
        self._room_types_path = Path(room_types_path)

    def load(self) -> Tuple[RoomTypeTintRGBA, ...]:
        """Le e valida a tabela, retorna uma tupla de tints RGBA indexada
        pelo mesmo `room_type` gerado por `DungeonGenerator`.

        Levanta `RoomTypeDefinitionError` se o arquivo nao existir, estiver
        malformado, ou tiver menos entradas do que `ROOM_TYPE_COUNT` (faria
        um `room_type` valido gerado pelo dungeon nao ter tint correspondente).
        """
        if not self._room_types_path.is_file():
            raise RoomTypeDefinitionError(
                f"arquivo de tipos de sala nao encontrado em {self._room_types_path}"
            )
        with self._room_types_path.open("r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RoomTypeDefinitionError(f"JSON invalido em {self._room_types_path}: {exc}") from exc

        if not isinstance(data, list):
            raise RoomTypeDefinitionError(
                f"{self._room_types_path} deve conter uma lista JSON no nivel raiz"
            )
        if len(data) < ROOM_TYPE_COUNT:
            raise RoomTypeDefinitionError(
                f"{self._room_types_path} tem {len(data)} tipo(s) de sala, mas "
                f"DungeonGenerator gera room_type em [0, {ROOM_TYPE_COUNT})"
            )

        tints = []
        for entry in data:
            tint = entry["tint_rgba"]
            if len(tint) != 4:
                raise RoomTypeDefinitionError(
                    f"'tint_rgba' deve ter 4 componentes (R,G,B,A) em {self._room_types_path}"
                )
            tints.append(tuple(int(component) for component in tint))
        return tuple(tints)
