# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import numpy as np
import pytest

from ouroboros.core.memory.handles import unpack_generation, unpack_index
from ouroboros.core.memory.memory_manager import MemoryManager

TRANSFORM_LIKE_DTYPE = np.dtype([("x", np.float32)])
VELOCITY_LIKE_DTYPE = np.dtype([("vx", np.float32)])


def test_create_pool_and_get_pool_return_same_instance():
    mm = MemoryManager(entity_capacity=8)
    pool = mm.create_pool("transform", TRANSFORM_LIKE_DTYPE)
    assert mm.get_pool("transform") is pool
    assert mm.has_pool("transform")
    assert not mm.has_pool("velocity")


def test_create_pool_duplicate_name_raises():
    mm = MemoryManager(entity_capacity=8)
    mm.create_pool("transform", TRANSFORM_LIKE_DTYPE)
    with pytest.raises(ValueError):
        mm.create_pool("transform", TRANSFORM_LIKE_DTYPE)


def test_acquire_entity_returns_unique_packed_ids():
    mm = MemoryManager(entity_capacity=4)
    handles = [mm.acquire_entity() for _ in range(4)]
    assert len(set(handles)) == 4


def test_acquire_entity_beyond_capacity_raises():
    mm = MemoryManager(entity_capacity=2)
    mm.acquire_entity()
    mm.acquire_entity()
    with pytest.raises(IndexError):
        mm.acquire_entity()


def test_is_alive_true_for_fresh_handle_false_after_release():
    mm = MemoryManager(entity_capacity=4)
    handle = mm.acquire_entity()
    assert mm.is_alive(handle)
    mm.release_entity(handle)
    assert not mm.is_alive(handle)


def test_release_bumps_generation_and_invalidates_stale_handle():
    mm = MemoryManager(entity_capacity=1)
    handle_gen0 = mm.acquire_entity()
    mm.release_entity(handle_gen0)
    handle_gen1 = mm.acquire_entity()

    assert unpack_index(handle_gen0) == unpack_index(handle_gen1)
    assert unpack_generation(handle_gen1) == unpack_generation(handle_gen0) + 1
    assert not mm.is_alive(handle_gen0)
    assert mm.is_alive(handle_gen1)


def test_release_entity_is_noop_for_already_stale_handle():
    mm = MemoryManager(entity_capacity=1)
    handle_gen0 = mm.acquire_entity()
    mm.release_entity(handle_gen0)
    handle_gen1 = mm.acquire_entity()  # generation bumps to 1, index reused

    mm.release_entity(handle_gen0)  # stale handle -- must not double-free the slot

    # If the stale release had incorrectly freed the slot again, capacity
    # (1) would allow a second acquire here even though handle_gen1 was
    # never released -- it must not.
    with pytest.raises(IndexError):
        mm.acquire_entity()
    assert mm.is_alive(handle_gen1)


def test_release_detaches_entity_from_all_registered_pools():
    mm = MemoryManager(entity_capacity=4)
    transform_pool = mm.create_pool("transform", TRANSFORM_LIKE_DTYPE)
    velocity_pool = mm.create_pool("velocity", VELOCITY_LIKE_DTYPE)

    handle = mm.acquire_entity()
    index = unpack_index(handle)
    transform_pool.attach(index)
    velocity_pool.attach(index)

    mm.release_entity(handle)

    assert not transform_pool.is_attached(index)
    assert not velocity_pool.is_attached(index)


def test_is_alive_batch_matches_scalar_is_alive():
    mm = MemoryManager(entity_capacity=8)
    handles = [mm.acquire_entity() for _ in range(4)]
    mm.release_entity(handles[1])
    packed = np.array(handles, dtype=np.uint64)

    result = mm.is_alive_batch(packed)

    expected = [mm.is_alive(h) if i != 1 else False for i, h in enumerate(handles)]
    # handles[1] itself is now stale; is_alive(handles[1]) already reflects that.
    expected = [mm.is_alive(h) for h in handles]
    assert result.tolist() == expected
    assert result.tolist() == [True, False, True, True]


def test_multiple_pools_share_the_same_global_entity_index_space():
    mm = MemoryManager(entity_capacity=4)
    pool_a = mm.create_pool("a", TRANSFORM_LIKE_DTYPE)
    pool_b = mm.create_pool("b", VELOCITY_LIKE_DTYPE)

    handle = mm.acquire_entity()
    index = unpack_index(handle)
    pool_a.attach(index)
    # pool_b never attaches -- must not silently share a row with pool_a
    assert pool_a.is_attached(index)
    assert not pool_b.is_attached(index)
