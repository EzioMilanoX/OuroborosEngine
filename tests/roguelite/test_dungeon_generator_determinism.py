# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de determinismo/consistencia estrutural de DungeonGenerator (Pilar 3)."""
from __future__ import annotations

import numpy as np

from ouroboros.roguelite.generation.dungeon_generator import DungeonGenerator
from ouroboros.roguelite.generation.random import StrictRandom


def _make_generator() -> DungeonGenerator:
    return DungeonGenerator(max_rooms=8, room_size_range=(4, 8))


def test_same_seed_and_level_seed_produce_byte_identical_layout() -> None:
    layout_a = _make_generator().generate(StrictRandom(root_seed=100), level_seed=3)
    layout_b = _make_generator().generate(StrictRandom(root_seed=100), level_seed=3)

    np.testing.assert_array_equal(layout_a.rooms, layout_b.rooms)
    np.testing.assert_array_equal(layout_a.tiles, layout_b.tiles)
    assert layout_a.seed == layout_b.seed == 100
    assert layout_a.algorithm_version == layout_b.algorithm_version


def test_generating_a_level_in_isolation_matches_generating_it_after_others() -> None:
    """Particionar por salt=level_seed garante que gerar o nivel 7
    isoladamente produza o mesmo resultado que gera-lo depois de ja ter
    gerado os niveis 1-6 (mesma StrictRandom, usada para varios niveis)."""
    generator = _make_generator()
    strict_random = StrictRandom(root_seed=777)

    for level_seed in range(1, 7):
        generator.generate(strict_random, level_seed=level_seed)

    layout_after_others = generator.generate(strict_random, level_seed=7)
    layout_in_isolation = _make_generator().generate(StrictRandom(root_seed=777), level_seed=7)

    np.testing.assert_array_equal(layout_after_others.rooms, layout_in_isolation.rooms)
    np.testing.assert_array_equal(layout_after_others.tiles, layout_in_isolation.tiles)


def test_different_root_seed_produces_different_layout() -> None:
    layout_a = _make_generator().generate(StrictRandom(root_seed=1), level_seed=1)
    layout_b = _make_generator().generate(StrictRandom(root_seed=2), level_seed=1)

    assert not np.array_equal(layout_a.rooms, layout_b.rooms)


def test_different_level_seed_produces_different_layout() -> None:
    strict_random = StrictRandom(root_seed=1)
    layout_a = _make_generator().generate(strict_random, level_seed=1)
    layout_b = _make_generator().generate(strict_random, level_seed=2)

    assert not np.array_equal(layout_a.rooms, layout_b.rooms)


def test_room_count_and_tile_offsets_are_consistent_with_tiles_array() -> None:
    layout = _make_generator().generate(StrictRandom(root_seed=55), level_seed=9)

    assert layout.rooms.shape[0] == 8

    total_tiles = layout.tiles.shape[0]
    for room in layout.rooms:
        offset = int(room["tile_offset"])
        count = int(room["tile_count"])
        assert count > 0
        assert 0 <= offset
        assert offset + count <= total_tiles

        room_tiles = layout.tiles[offset : offset + count]
        # Toda fatia de tiles de uma sala deve pertencer exclusivamente a ela.
        assert np.all(room_tiles["room_id"] == room["room_id"])

    # As fatias, concatenadas na ordem das salas, cobrem o array inteiro
    # sem sobreposicao (tile_offset[i+1] == tile_offset[i] + tile_count[i]).
    sorted_by_offset = np.sort(layout.rooms, order="tile_offset")
    expected_offset = 0
    for room in sorted_by_offset:
        assert int(room["tile_offset"]) == expected_offset
        expected_offset += int(room["tile_count"])
    assert expected_offset == total_tiles


def test_rooms_do_not_overlap() -> None:
    layout = _make_generator().generate(StrictRandom(root_seed=321), level_seed=4)
    rooms = layout.rooms

    for i in range(rooms.shape[0]):
        for j in range(i + 1, rooms.shape[0]):
            a = rooms[i]
            b = rooms[j]
            overlap_x = int(a["grid_x"]) < int(b["grid_x"]) + int(b["width"]) and int(a["grid_x"]) + int(
                a["width"]
            ) > int(b["grid_x"])
            overlap_y = int(a["grid_y"]) < int(b["grid_y"]) + int(b["height"]) and int(a["grid_y"]) + int(
                a["height"]
            ) > int(b["grid_y"])
            assert not (overlap_x and overlap_y), f"rooms {i} and {j} overlap"


def test_algorithm_version_is_stamped_on_layout() -> None:
    layout = _make_generator().generate(StrictRandom(root_seed=1), level_seed=1)
    assert layout.algorithm_version == DungeonGenerator.ALGORITHM_VERSION
