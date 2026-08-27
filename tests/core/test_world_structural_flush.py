# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import numpy as np

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.collision_system import CollisionSystem


def test_world_create_pool_is_a_passthrough_to_memory_manager(memory_manager, world):
    dtype = np.dtype([("lane", np.int8)])

    pool = world.create_pool("lane", dtype)

    assert pool is memory_manager.get_pool("lane")
    assert world.get_pool("lane") is pool
    assert world.has_pool("lane")
    assert not world.has_pool("nonexistent_pool_name")


def test_world_pack_current_is_a_passthrough_to_memory_manager(memory_manager, world):
    world.register_archetype("thing", ("transform",))
    handle = world.create_entity("thing")
    index = unpack_index(handle)

    assert world.pack_current(index) == memory_manager.pack_current(index)
    assert world.pack_current(index) == handle


def test_create_entity_is_immediate():
    from ouroboros.core.memory.memory_manager import MemoryManager
    from ouroboros.core.components.schemas import TRANSFORM_DTYPE
    from ouroboros.core.world import World

    mm = MemoryManager(entity_capacity=8)
    mm.create_pool("transform", TRANSFORM_DTYPE)
    world = World(mm)
    world.register_archetype("thing", ("transform",))

    handle = world.create_entity("thing")

    # No step()/flush() needed -- create_entity takes effect immediately.
    assert world.is_alive(handle)
    assert world.get_pool("transform").is_attached(unpack_index(handle))


def test_destroy_entity_is_deferred_until_flush(world):
    world.register_archetype("thing", ("transform",))
    handle = world.create_entity("thing")

    world.destroy_entity(handle)

    assert world.is_alive(handle)  # still alive: flush() has not run yet
    assert world.get_pool("transform").is_attached(unpack_index(handle))

    world.flush()

    assert not world.is_alive(handle)
    assert not world.get_pool("transform").is_attached(unpack_index(handle))


def test_step_calls_systems_then_flushes_exactly_once(world):
    calls = []

    class RecordingSystem:
        def update(self, world, delta_time):
            calls.append(delta_time)

    world.register_system(RecordingSystem())
    world.step(0.5)

    assert calls == [0.5]


def test_collision_pairs_survive_destroy_within_same_frame(memory_manager, world):
    """
    A system earlier in the frame (CollisionSystem) captures a pair of
    entity indices; a later system may call destroy_entity on one of
    them. Because destroy is deferred to flush() at the end of step(),
    the collision pair captured earlier in the SAME frame must remain a
    valid, readable array -- it must not be silently corrupted by the
    swap-remove that would happen if destroy were immediate.
    """
    world.register_archetype("box", ("transform", "hitbox"))
    collision_system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=16)

    destroyed_this_frame = []

    class DestroyerSystem:
        def update(self, inner_world, delta_time):
            pairs = collision_system.get_collision_pairs()
            if pairs.shape[0] > 0:
                target_index = int(pairs[0, 0])
                handle = handle_by_index[target_index]
                inner_world.destroy_entity(handle)
                destroyed_this_frame.append(target_index)

    world.register_system(collision_system)
    world.register_system(DestroyerSystem())

    handle_by_index = {}
    for x, y in [(0.0, 0.0), (1.0, 0.0)]:
        handle = world.create_entity("box")
        index = unpack_index(handle)
        handle_by_index[index] = handle
        transform_pool = world.get_pool("transform")
        hitbox_pool = world.get_pool("hitbox")
        t_row = transform_pool.dense_row_of(index)
        transform_pool.active_view()["position_x"][t_row] = x
        transform_pool.active_view()["position_y"][t_row] = y
        h_row = hitbox_pool.dense_row_of(index)
        hitbox_pool.active_view()["half_width"][h_row] = 1.0
        hitbox_pool.active_view()["half_height"][h_row] = 1.0
        hitbox_pool.active_view()["collision_layer"][h_row] = 1
        hitbox_pool.active_view()["collision_mask"][h_row] = 1

    world.step(0.016)

    assert len(destroyed_this_frame) == 1
    destroyed_index = destroyed_this_frame[0]
    assert not world.is_alive(handle_by_index[destroyed_index])
