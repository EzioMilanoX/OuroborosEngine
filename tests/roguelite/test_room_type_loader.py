# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de RoomTypeLoader (Pilar 3): carga real de data/room_types.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.roguelite.generation.dungeon_generator import ROOM_TYPE_COUNT
from ouroboros.roguelite.loaders.room_type_loader import RoomTypeDefinitionError, RoomTypeLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ROOM_TYPES_PATH = REPO_ROOT / "data" / "room_types.json"


def test_load_real_room_types_covers_every_room_type_dungeon_generator_produces() -> None:
    loader = RoomTypeLoader(REAL_ROOM_TYPES_PATH)
    tints = loader.load()

    assert len(tints) >= ROOM_TYPE_COUNT
    for tint in tints:
        assert len(tint) == 4
        for component in tint:
            assert 0 <= component <= 255


def test_load_missing_file_raises(tmp_path) -> None:
    loader = RoomTypeLoader(tmp_path / "does_not_exist.json")
    with pytest.raises(RoomTypeDefinitionError):
        loader.load()


def test_load_malformed_json_raises(tmp_path) -> None:
    path = tmp_path / "room_types.json"
    path.write_text("{not valid json", encoding="utf-8")
    loader = RoomTypeLoader(path)
    with pytest.raises(RoomTypeDefinitionError):
        loader.load()


def test_load_raises_when_not_a_list(tmp_path) -> None:
    path = tmp_path / "room_types.json"
    path.write_text(json.dumps({"name": "standard", "tint_rgba": [1, 2, 3, 4]}), encoding="utf-8")
    loader = RoomTypeLoader(path)
    with pytest.raises(RoomTypeDefinitionError):
        loader.load()


def test_load_raises_when_fewer_entries_than_room_type_count(tmp_path) -> None:
    path = tmp_path / "room_types.json"
    path.write_text(json.dumps([{"name": "standard", "tint_rgba": [1, 2, 3, 4]}]), encoding="utf-8")
    loader = RoomTypeLoader(path)
    with pytest.raises(RoomTypeDefinitionError):
        loader.load()


def test_load_returns_tints_in_file_order(tmp_path) -> None:
    path = tmp_path / "room_types.json"
    entries = [{"name": f"type_{i}", "tint_rgba": [i, i, i, 255]} for i in range(ROOM_TYPE_COUNT)]
    path.write_text(json.dumps(entries), encoding="utf-8")
    loader = RoomTypeLoader(path)

    tints = loader.load()

    assert tints == tuple((i, i, i, 255) for i in range(ROOM_TYPE_COUNT))
