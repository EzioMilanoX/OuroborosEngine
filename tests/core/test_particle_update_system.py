# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa ParticleUpdateSystem: roda ParticleStorage.update() de verdade via World.step()."""
from __future__ import annotations

import numpy as np

from ouroboros.core.particle_storage import ParticleStorage
from ouroboros.core.systems.particle_update_system import ParticleUpdateSystem


def test_particle_update_system_advances_particles_via_world_step(world):
    storage = ParticleStorage(capacity=10)
    storage.emit_burst(
        position_x=np.array([0.0], dtype=np.float32),
        position_y=np.array([0.0], dtype=np.float32),
        velocity_x=np.array([2.0], dtype=np.float32),
        velocity_y=np.array([0.0], dtype=np.float32),
        ttl_seconds=np.array([1.0], dtype=np.float32),
        size=np.array([4.0], dtype=np.float32),
        tint_rgba=np.array([[255, 255, 255, 255]], dtype=np.uint8),
    )
    world.register_system(ParticleUpdateSystem(storage))

    world.step(0.5)

    assert storage.count == 1
    assert float(storage.active_view()["position_x"][0]) == 1.0


def test_particle_update_system_removes_expired_particles_via_world_step(world):
    storage = ParticleStorage(capacity=10)
    storage.emit_burst(
        position_x=np.array([0.0], dtype=np.float32),
        position_y=np.array([0.0], dtype=np.float32),
        velocity_x=np.array([0.0], dtype=np.float32),
        velocity_y=np.array([0.0], dtype=np.float32),
        ttl_seconds=np.array([0.1], dtype=np.float32),
        size=np.array([4.0], dtype=np.float32),
        tint_rgba=np.array([[255, 255, 255, 255]], dtype=np.uint8),
    )
    world.register_system(ParticleUpdateSystem(storage))

    world.step(0.5)

    assert storage.count == 0
