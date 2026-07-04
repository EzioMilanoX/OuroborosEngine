import numpy as np

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.core.systems.spatial_grid import UniformGrid


def make_box(world, x, y, half_size=1.0, layer=1, mask=1):
    handle = world.create_entity("box")
    index = unpack_index(handle)
    transform_pool = world.get_pool("transform")
    hitbox_pool = world.get_pool("hitbox")

    t_row = transform_pool.dense_row_of(index)
    transform_pool.active_view()["position_x"][t_row] = x
    transform_pool.active_view()["position_y"][t_row] = y

    h_row = hitbox_pool.dense_row_of(index)
    hitbox_pool.active_view()["half_width"][h_row] = half_size
    hitbox_pool.active_view()["half_height"][h_row] = half_size
    hitbox_pool.active_view()["collision_layer"][h_row] = layer
    hitbox_pool.active_view()["collision_mask"][h_row] = mask

    return handle


def test_two_overlapping_boxes_produce_one_pair(memory_manager, world):
    world.register_archetype("box", ("transform", "hitbox"))
    system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=16)
    world.register_system(system)

    h1 = make_box(world, 0.0, 0.0)
    h2 = make_box(world, 1.0, 0.0)

    world.step(0.016)

    pairs = system.get_collision_pairs()
    assert pairs.shape[0] == 1
    assert set(pairs[0].tolist()) == {unpack_index(h1), unpack_index(h2)}


def test_far_apart_boxes_produce_no_pairs(memory_manager, world):
    world.register_archetype("box", ("transform", "hitbox"))
    system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=16)
    world.register_system(system)

    make_box(world, 0.0, 0.0)
    make_box(world, 1000.0, 1000.0)

    world.step(0.016)

    assert system.get_collision_pairs().shape[0] == 0


def test_collision_mask_filters_out_non_interacting_layers(memory_manager, world):
    world.register_archetype("box", ("transform", "hitbox"))
    system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=16)
    world.register_system(system)

    # overlapping in space, but neither layer is in the other's mask
    make_box(world, 0.0, 0.0, layer=1, mask=0)
    make_box(world, 0.5, 0.0, layer=2, mask=0)

    world.step(0.016)

    assert system.get_collision_pairs().shape[0] == 0


def test_max_pairs_caps_reported_collisions(memory_manager, world):
    world.register_archetype("box", ("transform", "hitbox"))
    system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=1)
    world.register_system(system)

    # three mutually overlapping boxes -> 3 candidate pairs, only 1 fits
    for i in range(3):
        make_box(world, float(i) * 0.1, 0.0)

    world.step(0.016)

    assert system.get_collision_pairs().shape[0] == 1


def test_spatial_grid_agrees_with_brute_force():
    from ouroboros.core.memory.memory_manager import MemoryManager
    from ouroboros.core.world import World
    from ouroboros.core.components.schemas import TRANSFORM_DTYPE, HITBOX_DTYPE

    mm = MemoryManager(entity_capacity=64)
    mm.create_pool("transform", TRANSFORM_DTYPE)
    mm.create_pool("hitbox", HITBOX_DTYPE)
    world = World(mm)
    world.register_archetype("box", ("transform", "hitbox"))

    positions = [(0, 0), (1, 0), (50, 50), (51, 50), (100, 0)]
    for x, y in positions:
        make_box(world, x, y)

    brute = CollisionSystem(mm, "transform", "hitbox", max_pairs=64)
    grid = UniformGrid(world_bounds=(0, 0, 200, 200), cell_size=8, entity_capacity=64, max_candidate_pairs=64)
    accelerated = CollisionSystem(mm, "transform", "hitbox", max_pairs=64, spatial_grid=grid)

    brute.update(world, 0.016)
    accelerated.update(world, 0.016)

    brute_pairs = {frozenset(p) for p in brute.get_collision_pairs().tolist()}
    grid_pairs = {frozenset(p) for p in accelerated.get_collision_pairs().tolist()}
    assert brute_pairs == grid_pairs
    assert len(brute_pairs) == 2  # (0,0)-(1,0) and (50,50)-(51,50)
