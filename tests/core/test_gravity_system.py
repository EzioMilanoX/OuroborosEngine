# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa GravitySystem: soma gravity_y*dt em velocity.linear_y de toda entidade com a pool."""
from __future__ import annotations

import pytest

from ouroboros.core.systems.gravity_system import GravitySystem


def test_gravity_accumulates_into_linear_y_via_world_step(memory_manager, world):
    world.register_archetype("faller", ("velocity",))
    packed = world.create_entity("faller")
    from ouroboros.core.memory.handles import unpack_index
    index = unpack_index(packed)

    world.register_system(GravitySystem(memory_manager, gravity_y=100.0))

    world.step(0.1)

    velocity_pool = world.get_pool("velocity")
    row = velocity_pool.dense_row_of(index)
    assert velocity_pool.active_view()["linear_y"][row] == pytest.approx(10.0)


def test_gravity_accumulates_across_multiple_steps(memory_manager, world):
    world.register_archetype("faller", ("velocity",))
    packed = world.create_entity("faller")
    from ouroboros.core.memory.handles import unpack_index
    index = unpack_index(packed)

    world.register_system(GravitySystem(memory_manager, gravity_y=100.0))

    world.step(0.1)
    world.step(0.1)

    velocity_pool = world.get_pool("velocity")
    row = velocity_pool.dense_row_of(index)
    assert velocity_pool.active_view()["linear_y"][row] == pytest.approx(20.0)


def test_negative_gravity_y_pulls_upward_on_screen(memory_manager, world):
    """Prova que GravitySystem nao assume um sinal fixo -- um produto que use
    +y=cima poderia passar gravity_y negativo."""
    world.register_archetype("faller", ("velocity",))
    packed = world.create_entity("faller")
    from ouroboros.core.memory.handles import unpack_index
    index = unpack_index(packed)

    world.register_system(GravitySystem(memory_manager, gravity_y=-50.0))

    world.step(0.1)

    velocity_pool = world.get_pool("velocity")
    row = velocity_pool.dense_row_of(index)
    assert velocity_pool.active_view()["linear_y"][row] == pytest.approx(-5.0)
