# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa ScreenShake: offset decai ao longo da duracao, expira, magnitude limitada pela intensidade."""
from __future__ import annotations

from ouroboros.bootstrap.screen_shake import ScreenShake, ScreenShakeUpdateSystem
from ouroboros.interfaces.null.null_renderer import NullRenderer


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


def test_current_magnitude_is_zero_before_any_trigger():
    shake = ScreenShake()

    assert shake.current_magnitude() == 0.0


def test_current_magnitude_reflects_decay_without_advancing_time():
    shake = ScreenShake()
    shake.trigger(intensity=10.0, duration_seconds=1.0)

    assert shake.current_magnitude() == 10.0
    assert shake.current_magnitude() == 10.0  # consultar de novo nao avanca nada

    shake.update(0.4)  # so update() avanca o tempo

    assert abs(shake.current_magnitude() - 6.0) < 1e-6


def test_current_magnitude_is_zero_once_expired():
    shake = ScreenShake()
    shake.trigger(intensity=10.0, duration_seconds=0.2)

    shake.update(0.25)  # ultrapassa a duracao total

    assert shake.current_magnitude() == 0.0


def test_additive_stacking_via_current_magnitude_matches_a_constant_decay_rate():
    """Prova do padrao usado pelo BulletHell (repo irmao): somar um novo evento
    ao shake ja em andamento, mantendo a MESMA taxa de decaimento (aqui 26/s),
    via `trigger(novo_total, novo_total/taxa)` -- current_magnitude() sempre
    reflete o total corretamente decaido, nunca o valor do trigger original."""
    DECAY_RATE = 26.0
    shake = ScreenShake()

    def add_shake(amount: float, cap: float = 18.0) -> None:
        new_total = min(shake.current_magnitude() + amount, cap)
        shake.trigger(new_total, new_total / DECAY_RATE)

    add_shake(10.0)
    assert shake.current_magnitude() == 10.0

    shake.update(4.0 / DECAY_RATE)  # decai 4.0 unidades -- sobra 6.0
    assert abs(shake.current_magnitude() - 6.0) < 1e-6

    add_shake(5.0)  # soma aos 6.0 remanescentes, nao aos 10.0 originais
    assert abs(shake.current_magnitude() - 11.0) < 1e-6

    add_shake(20.0)  # estouraria o teto -- fica clampado em 18.0
    assert shake.current_magnitude() == 18.0


def test_screen_shake_update_system_forwards_the_decayed_offset_to_the_renderer(world):
    shake = ScreenShake(rng=lambda: 1.0)
    shake.trigger(intensity=10.0, duration_seconds=1.0)
    renderer = NullRenderer()
    world.register_system(ScreenShakeUpdateSystem(shake, renderer))

    world.step(0.5)  # metade da duracao decorrida -- offset esperado = 5.0

    assert renderer.camera_offset == (5.0, 5.0)
