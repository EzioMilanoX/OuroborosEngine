# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Posiciona notas em scroll vertical em sincronia com o audio real, via IAudioClock."""
from __future__ import annotations

from typing import Tuple

import numpy as np

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock


class NoteScrollSystem(ISystem):
    """
    Atualiza `transform.position_x`/`position_y` de toda nota ativa como
    funcao PURA do tempo real restante ate seu instante de disparo --
    NUNCA integrando `delta_time`, exatamente como `RhythmSpawnerSystem`
    nunca acumula `delta_time` para decidir o que disparar.

    A cada `update()`, para cada entidade com `note_state`+`transform`+
    `lane` anexados::

        time_until_hit = note_state.timestamp_seconds - effective_time
        position_y = judgment_line_y - time_until_hit * scroll_speed_px_per_sec
        position_x = lane_x_positions[lane]

    `effective_time` usa a MESMA formula de compensacao de latencia de
    `RhythmSpawnerSystem._compute_effective_time`
    (`max(0.0, audio_clock.now_seconds() - audio_clock.get_output_latency_seconds())`).
    Por ser recalculada do zero a cada frame a partir do relogio de
    audio real (nunca por integracao de `delta_time`), a posicao de uma
    nota nao pode dessincronizar/derivar mesmo sob variacao de frame
    rate: ela e sempre exatamente onde deveria estar para o instante de
    audio atual, nunca "quase la" por acumulo de erro.

    Convencao de eixo Y (tela, y cresce para baixo): `time_until_hit`
    positivo (nota ainda por vir) fica ACIMA de `judgment_line_y`;
    `time_until_hit == 0` fica EXATAMENTE em `judgment_line_y`;
    `time_until_hit` negativo (nota ja vencida) continua descendo abaixo
    da linha ate `JudgmentSystem` a remover (auto-erro).

    Invariante Zero-GC: totalmente vetorizado sobre a interseccao das
    tres pools via `intersect_entity_indices` (um array novo por
    CHAMADA, nao por entidade -- o mesmo padrao ja aceito em
    `PhysicsSystem`/`CollisionSystem`); nenhum objeto Python instanciado
    por nota.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        note_state_pool_name: str,
        transform_pool_name: str,
        lane_pool_name: str,
        lane_x_positions: Tuple[float, ...],
        judgment_line_y: float,
        scroll_speed_px_per_sec: float,
    ) -> None:
        """Resolve nomes de pool para instancias uma unica vez (fora do
        hot-loop) e converte `lane_x_positions` para `np.ndarray` uma
        unica vez (nunca reconstruida a cada `update()`)."""
        self._audio_clock = audio_clock
        self._note_state_pool_name = note_state_pool_name
        self._transform_pool_name = transform_pool_name
        self._lane_pool_name = lane_pool_name
        self._lane_x_positions = np.array(lane_x_positions, dtype=np.float32)
        self._judgment_line_y = judgment_line_y
        self._scroll_speed_px_per_sec = scroll_speed_px_per_sec

    def update(self, world: World, delta_time: float) -> None:
        """Reposiciona toda nota ativa; `delta_time` e recebido apenas
        para respeitar a assinatura de `ISystem.update` e e explicitamente
        ignorado (ver docstring da classe)."""
        del delta_time  # deliberadamente ignorado -- ver docstring da classe

        note_state_pool = world.get_pool(self._note_state_pool_name)
        transform_pool = world.get_pool(self._transform_pool_name)
        lane_pool = world.get_pool(self._lane_pool_name)

        entity_indices = intersect_entity_indices(note_state_pool, transform_pool, lane_pool)
        if entity_indices.size == 0:
            return

        effective_time = max(
            0.0,
            self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds(),
        )

        ns_rows = note_state_pool.dense_rows_of(entity_indices)
        t_rows = transform_pool.dense_rows_of(entity_indices)
        l_rows = lane_pool.dense_rows_of(entity_indices)

        ns_view = note_state_pool.active_view()
        t_view = transform_pool.active_view()
        l_view = lane_pool.active_view()

        time_until_hit = ns_view["timestamp_seconds"][ns_rows] - effective_time
        t_view["position_y"][t_rows] = self._judgment_line_y - time_until_hit * self._scroll_speed_px_per_sec
        t_view["position_x"][t_rows] = self._lane_x_positions[l_view["lane"][l_rows]]
