# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.physics_system import PhysicsSystem
from ouroboros.core.world import World


def make_entity(world: World, position, velocity):
    handle = world.create_entity("mover")
    index = unpack_index(handle)
    transform_pool = world.get_pool("transform")
    velocity_pool = world.get_pool("velocity")

    t_row = transform_pool.dense_row_of(index)
    transform_pool.active_view()["position_x"][t_row] = position[0]
    transform_pool.active_view()["position_y"][t_row] = position[1]
    transform_pool.active_view()["rotation_rad"][t_row] = 0.0

    v_row = velocity_pool.dense_row_of(index)
    velocity_pool.active_view()["linear_x"][v_row] = velocity[0]
    velocity_pool.active_view()["linear_y"][v_row] = velocity[1]
    velocity_pool.active_view()["angular"][v_row] = velocity[2] if len(velocity) > 2 else 0.0

    return handle


def test_physics_system_integrates_position_by_velocity_times_dt(memory_manager, world):
    world.register_archetype("mover", ("transform", "velocity"))
    world.register_system(PhysicsSystem(memory_manager))

    handle = make_entity(world, position=(0.0, 0.0), velocity=(2.0, -1.0))
    index = unpack_index(handle)

    world.step(0.5)

    row = world.get_pool("transform").dense_row_of(index)
    view = world.get_pool("transform").active_view()
    assert view["position_x"][row] == 1.0
    assert view["position_y"][row] == -0.5


def test_physics_system_ignores_entities_missing_velocity(memory_manager, world):
    world.register_archetype("mover", ("transform", "velocity"))
    world.register_archetype("static", ("transform",))
    world.register_system(PhysicsSystem(memory_manager))

    handle = world.create_entity("static")
    index = unpack_index(handle)
    transform_pool = world.get_pool("transform")
    row = transform_pool.dense_row_of(index)
    transform_pool.active_view()["position_x"][row] = 5.0

    world.step(1.0)  # must not raise even though this entity has no velocity component

    assert transform_pool.active_view()["position_x"][row] == 5.0


def test_physics_system_updates_multiple_entities_independently(memory_manager, world):
    world.register_archetype("mover", ("transform", "velocity"))
    world.register_system(PhysicsSystem(memory_manager))

    h1 = make_entity(world, position=(0.0, 0.0), velocity=(1.0, 0.0))
    h2 = make_entity(world, position=(10.0, 10.0), velocity=(0.0, 3.0))

    world.step(2.0)

    transform_pool = world.get_pool("transform")
    view = transform_pool.active_view()
    row1 = transform_pool.dense_row_of(unpack_index(h1))
    row2 = transform_pool.dense_row_of(unpack_index(h2))
    assert view["position_x"][row1] == 2.0
    assert view["position_y"][row1] == 0.0
    assert view["position_x"][row2] == 10.0
    assert view["position_y"][row2] == 16.0
