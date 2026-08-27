# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa FxTtlSystem: decrementa ttl_seconds por delta_time real e destroi os expirados."""
from __future__ import annotations

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.fx_system import FxTtlSystem


def _spawn_fx(world, ttl_seconds: float) -> int:
    handle = world.create_entity("fx")
    index = unpack_index(handle)
    fx_pool = world.get_pool("fx")
    row = fx_pool.dense_row_of(index)
    fx_pool.active_view()["ttl_seconds"][row] = ttl_seconds
    return index


def test_ttl_decrements_by_real_delta_time(world):
    world.register_archetype("fx", ("fx",))
    world.register_system(FxTtlSystem())
    index = _spawn_fx(world, ttl_seconds=1.0)

    world.step(0.3)

    fx_pool = world.get_pool("fx")
    row = fx_pool.dense_row_of(index)
    assert abs(float(fx_pool.active_view()["ttl_seconds"][row]) - 0.7) < 1e-6


def test_entity_survives_while_ttl_still_positive(world):
    world.register_archetype("fx", ("fx",))
    world.register_system(FxTtlSystem())
    _spawn_fx(world, ttl_seconds=1.0)

    world.step(0.5)

    assert world.get_pool("fx").count == 1


def test_entity_is_destroyed_once_ttl_expires(world):
    world.register_archetype("fx", ("fx",))
    world.register_system(FxTtlSystem())
    _spawn_fx(world, ttl_seconds=0.2)

    world.step(0.5)  # ultrapassa o ttl -- destruicao e diferida ate o flush() do proprio step()

    assert world.get_pool("fx").count == 0


def test_multiple_entities_expire_independently(world):
    world.register_archetype("fx", ("fx",))
    world.register_system(FxTtlSystem())
    _spawn_fx(world, ttl_seconds=0.1)  # expira neste step
    surviving_index = _spawn_fx(world, ttl_seconds=5.0)  # sobrevive

    world.step(0.5)

    fx_pool = world.get_pool("fx")
    assert fx_pool.count == 1
    assert fx_pool.is_attached(surviving_index)


def test_empty_fx_pool_is_a_safe_noop(world):
    world.register_archetype("fx", ("fx",))
    system = FxTtlSystem()

    system.update(world, delta_time=1.0)  # nao deve levantar erro

    assert world.get_pool("fx").count == 0


def test_custom_fx_pool_name_is_respected(memory_manager, world):
    memory_manager.create_pool("particles", world.get_pool("fx").dtype)
    world.register_archetype("particle_fx", ("particles",))
    world.register_system(FxTtlSystem(fx_pool_name="particles"))

    handle = world.create_entity("particle_fx")
    index = unpack_index(handle)
    particles_pool = world.get_pool("particles")
    particles_pool.active_view()["ttl_seconds"][particles_pool.dense_row_of(index)] = 0.1

    world.step(0.5)

    assert particles_pool.count == 0
