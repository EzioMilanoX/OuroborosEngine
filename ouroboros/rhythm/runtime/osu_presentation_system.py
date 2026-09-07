# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Anima o anel de aproximacao e a bola de slider em sincronia com o audio real, via IAudioClock."""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, unpack_batch
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock

_EPSILON = 1.0e-6


class OsuPresentationSystem(ISystem):
    """
    Analogo puramente-apresentacao de `NoteScrollSystem` para o modo
    Osu! (ROADMAP M15): encolhe o anel de aproximacao de todo hit-object
    ainda nao clicado (de `ring_start_scale` ate `1.0`, exatamente na
    hora do hit) e move a bola de todo slider em tracking (interpolacao
    linear cabeca->cauda pela fracao decorrida de `duration_seconds`).
    NUNCA pontua, sempre recomputado do zero a partir de
    `IAudioClock` -- nunca integra `delta_time` (mesmo criterio de
    `NoteScrollSystem`).

    MASCARAMENTO OBRIGATORIO antes de resolver `ring_entity_id`/
    `ball_entity_id` (achado real da critica de M15): `NULL_PACKED_HANDLE`
    empacota `index = INVALID_ENTITY_INDEX` (`-1`), que via mascara de
    bits vira `0xFFFFFFFF` -- um indice POSITIVO enorme, nao `-1`. Um
    CIRCLE tem `ball_entity_id == NULL_PACKED_HANDLE` PERMANENTEMENTE
    (nunca ganha uma bola); resolver essa coluna inteira via
    `unpack_batch`/`dense_rows_of` SEM antes mascarar `!=
    NULL_PACKED_HANDLE` estoura `IndexError` no primeiro frame com
    qualquer CIRCLE em campo. Por isso os dois metodos abaixo SEMPRE
    constroem o subconjunto mascarado primeiro, nunca chamam
    `unpack_batch` sobre a coluna crua inteira.

    Invariante Zero-GC: totalmente vetorizado; nenhum objeto Python
    instanciado por hit-object.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        note_state_pool_name: str,
        transform_pool_name: str,
        approach_seconds: float,
        ring_start_scale: float,
        ring_end_scale: float = 1.0,
    ) -> None:
        """`approach_seconds`: mesma duracao usada por
        `split_spawn_and_hit_schedules` para deslocar spawn-time de
        hit-time -- o anel comeca em `ring_start_scale` no instante do
        spawn e encolhe linearmente ate `ring_end_scale` exatamente no
        instante do hit (`timestamp_seconds`)."""
        self._audio_clock = audio_clock
        self._note_state_pool_name = note_state_pool_name
        self._transform_pool_name = transform_pool_name
        self._approach_seconds = max(approach_seconds, _EPSILON)
        self._ring_start_scale = ring_start_scale
        self._ring_end_scale = ring_end_scale

    def update(self, world: World, delta_time: float) -> None:
        """Reposiciona/reescala toda entidade companheira ativa;
        `delta_time` e recebido apenas para respeitar a assinatura de
        `ISystem.update` e e explicitamente ignorado (ver docstring da
        classe)."""
        del delta_time  # deliberadamente ignorado -- ver docstring da classe

        note_state_pool = world.get_pool(self._note_state_pool_name)
        if note_state_pool.count == 0:
            return
        transform_pool = world.get_pool(self._transform_pool_name)
        view = note_state_pool.active_view()

        effective_time = max(
            0.0,
            self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds(),
        )

        self._update_rings(view, transform_pool, effective_time)
        self._update_balls(view, transform_pool, effective_time)

    def _update_rings(self, view: np.ndarray, transform_pool, effective_time: float) -> None:
        ring_ids = view["ring_entity_id"]
        mask = ring_ids != NULL_PACKED_HANDLE
        if not mask.any():
            return

        entity_indices, _generations = unpack_batch(ring_ids[mask])
        rows = transform_pool.dense_rows_of(entity_indices)

        time_until_hit = view["timestamp_seconds"][mask] - effective_time
        fraction = np.clip(time_until_hit / self._approach_seconds, 0.0, 1.0)
        scale = self._ring_end_scale + fraction * (self._ring_start_scale - self._ring_end_scale)

        t_view = transform_pool.active_view()
        t_view["scale_x"][rows] = scale
        t_view["scale_y"][rows] = scale

    def _update_balls(self, view: np.ndarray, transform_pool, effective_time: float) -> None:
        ball_ids = view["ball_entity_id"]
        mask = (ball_ids != NULL_PACKED_HANDLE) & view["is_tracking"]
        if not mask.any():
            return

        entity_indices, _generations = unpack_batch(ball_ids[mask])
        rows = transform_pool.dense_rows_of(entity_indices)

        elapsed = effective_time - view["timestamp_seconds"][mask]
        duration = np.maximum(view["duration_seconds"][mask], _EPSILON)
        fraction = np.clip(elapsed / duration, 0.0, 1.0)
        x = view["x"][mask] + fraction * (view["end_x"][mask] - view["x"][mask])
        y = view["y"][mask] + fraction * (view["end_y"][mask] - view["y"][mask])

        t_view = transform_pool.active_view()
        t_view["position_x"][rows] = x
        t_view["position_y"][rows] = y
