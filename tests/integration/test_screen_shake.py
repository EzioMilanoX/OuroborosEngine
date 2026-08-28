# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa ScreenShake: offset decai ao longo da duracao, expira, magnitude limitada pela intensidade."""
from __future__ import annotations

from ouroboros.bootstrap.screen_shake import ScreenShake


def test_no_shake_triggered_returns_zero_offset():
    shake = ScreenShake(rng=lambda: 1.0)

    assert shake.update(0.016) == (0.0, 0.0)


def test_triggered_shake_returns_nonzero_offset_bounded_by_intensity():
    shake = ScreenShake(rng=lambda: 1.0)  # rng fixo no maximo -- offset = intensidade exata
    shake.trigger(intensity=10.0, duration_seconds=1.0)

    dx, dy = shake.update(0.0)

    assert dx == 10.0
    assert dy == 10.0


def test_shake_decays_linearly_over_duration():
    shake = ScreenShake(rng=lambda: 1.0)
    shake.trigger(intensity=10.0, duration_seconds=1.0)

    dx_start, _ = shake.update(0.0)
    dx_mid, _ = shake.update(0.5)  # metade do tempo decorrido

    assert dx_mid < dx_start
    assert abs(dx_mid - 5.0) < 1e-6


def test_shake_expires_after_its_full_duration():
    shake = ScreenShake(rng=lambda: 1.0)
    shake.trigger(intensity=10.0, duration_seconds=0.2)

    shake.update(0.25)  # ultrapassa a duracao total

    assert shake.update(0.0) == (0.0, 0.0)


def test_retriggering_restarts_the_decay():
    shake = ScreenShake(rng=lambda: 1.0)
    shake.trigger(intensity=10.0, duration_seconds=1.0)
    shake.update(0.9)  # quase expirado

    shake.trigger(intensity=5.0, duration_seconds=1.0)  # reinicia
    dx, _ = shake.update(0.0)

    assert dx == 5.0
