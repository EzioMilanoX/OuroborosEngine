# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa ParticleStorage: emissao em lote, integracao vetorizada, morte por ttl."""
from __future__ import annotations

import numpy as np

from ouroboros.core.particle_storage import ParticleStorage


def _burst(n: int, ttl: float = 1.0):
    position_x = np.arange(n, dtype=np.float32)
    position_y = np.zeros(n, dtype=np.float32)
    velocity_x = np.full(n, 10.0, dtype=np.float32)
    velocity_y = np.full(n, -5.0, dtype=np.float32)
    ttl_seconds = np.full(n, ttl, dtype=np.float32)
    size = np.full(n, 4.0, dtype=np.float32)
    tint_rgba = np.tile(np.array([255, 128, 0, 255], dtype=np.uint8), (n, 1))
    return position_x, position_y, velocity_x, velocity_y, ttl_seconds, size, tint_rgba


def test_emit_burst_populates_the_requested_number_of_particles():
    storage = ParticleStorage(capacity=100)

    emitted = storage.emit_burst(*_burst(5))

    assert emitted == 5
    assert storage.count == 5
    view = storage.active_view()
    assert view["position_x"].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert (view["velocity_x"] == 10.0).all()
    assert (view["tint_r"] == 255).all()


def test_emit_burst_truncates_silently_when_exceeding_capacity():
    storage = ParticleStorage(capacity=3)

    emitted = storage.emit_burst(*_burst(10))

    assert emitted == 3
    assert storage.count == 3


def test_emit_burst_accumulates_across_multiple_calls():
    storage = ParticleStorage(capacity=100)
    storage.emit_burst(*_burst(2))
    storage.emit_burst(*_burst(3))

    assert storage.count == 5


def test_update_integrates_position_by_velocity_and_decrements_ttl():
    storage = ParticleStorage(capacity=10)
    storage.emit_burst(*_burst(1, ttl=1.0))

    storage.update(0.5)

    view = storage.active_view()
    assert view["position_x"][0] == 5.0  # 0 + 10*0.5
    assert view["position_y"][0] == -2.5  # 0 + (-5)*0.5
    assert abs(float(view["ttl_seconds"][0]) - 0.5) < 1e-6


def test_update_removes_expired_particles_and_keeps_alive_ones():
    storage = ParticleStorage(capacity=10)
    storage.emit_burst(*_burst(1, ttl=0.1))  # expira logo
    storage.emit_burst(*_burst(1, ttl=5.0))  # sobrevive

    storage.update(0.5)

    assert storage.count == 1
    assert float(storage.active_view()["ttl_seconds"][0]) < 5.0


def test_update_on_empty_storage_is_a_safe_noop():
    storage = ParticleStorage(capacity=10)

    storage.update(1.0)  # nao deve levantar erro

    assert storage.count == 0


def test_update_when_nothing_expires_does_not_change_count():
    storage = ParticleStorage(capacity=10)
    storage.emit_burst(*_burst(4, ttl=100.0))

    storage.update(0.016)

    assert storage.count == 4
