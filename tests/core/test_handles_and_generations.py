# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import numpy as np

from ouroboros.core.memory.handles import (
    EntityHandle,
    NULL_PACKED_HANDLE,
    pack_batch,
    unpack_batch,
    unpack_generation,
    unpack_index,
)


def test_pack_raw_and_unpack_roundtrip():
    packed = EntityHandle.pack_raw(index=42, generation=7)
    assert unpack_index(packed) == 42
    assert unpack_generation(packed) == 7


def test_pack_and_unpack_via_entity_handle():
    handle = EntityHandle(index=5, generation=3)
    packed = handle.pack()
    assert EntityHandle.unpack(packed) == handle


def test_is_null():
    assert EntityHandle(index=-1, generation=0).is_null()
    assert not EntityHandle(index=0, generation=0).is_null()


def test_null_packed_handle_never_collides_with_small_indices():
    for index in range(0, 100):
        packed = EntityHandle.pack_raw(index, 0)
        assert packed != NULL_PACKED_HANDLE


def test_pack_batch_matches_scalar_pack_raw():
    indices = np.array([0, 1, 2, 65535], dtype=np.int64)
    generations = np.array([0, 1, 2, 3], dtype=np.int64)
    packed = pack_batch(indices, generations)
    for i in range(len(indices)):
        assert int(packed[i]) == EntityHandle.pack_raw(int(indices[i]), int(generations[i]))


def test_unpack_batch_matches_scalar_unpack():
    packed = np.array(
        [EntityHandle.pack_raw(i, g) for i, g in [(0, 0), (10, 5), (65535, 1)]],
        dtype=np.uint64,
    )
    indices, generations = unpack_batch(packed)
    assert list(indices) == [0, 10, 65535]
    assert list(generations) == [0, 5, 1]


def test_unpack_after_generation_increment_differs():
    packed_gen0 = EntityHandle.pack_raw(index=3, generation=0)
    packed_gen1 = EntityHandle.pack_raw(index=3, generation=1)
    assert packed_gen0 != packed_gen1
    assert unpack_index(packed_gen0) == unpack_index(packed_gen1) == 3
    assert unpack_generation(packed_gen1) == unpack_generation(packed_gen0) + 1
