# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dispara criacao de hit-objects Osu! em sincronia com o audio real, via IAudioClock."""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, PackedEntityId, unpack_index
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock


class OsuSpawnerSystem(ISystem):
    """Dispara a criacao de hit-objects Osu! em sincronia com a
    reproducao de audio real -- COPIA AUTONOMA da logica de cursor/
    `searchsorted` de `RhythmSpawnerSystem` (ROADMAP M15: os sistemas de
    ritmo desta engine nao compartilham base alem de `ISystem`; duplicar
    esta logica ja testada evita arriscar o caminho lane-mode via
    refactor). Ver docstring de `RhythmSpawnerSystem` para a formula de
    compensacao de latencia e o mecanismo de cursor monotonico -- IDENTICOS
    aqui, so o array consumido (`OSU_SCHEDULED_HIT_DTYPE`) e a pool
    escrita (`osu_note_state`) mudam.

    Invariante Zero-GC dentro de `update()`: mesma disciplina de
    `RhythmSpawnerSystem` -- `PackedEntityId` primitivos, slicing/
    aritmetica de indices inteiros, sem list comprehension nem
    `.append()` em loop quente.
    """

    def __init__(
        self,
        audio_clock: IAudioClock,
        scheduled_hits: np.ndarray,
        hit_archetype_name: str,
        osu_note_state_pool_name: str,
        max_hits_per_frame: Optional[int] = None,
        on_hit_object_spawned: Optional[
            Callable[[World, PackedEntityId, int, float, float, float, float, float, int], None]
        ] = None,
        hit_times: Optional[np.ndarray] = None,
    ) -> None:
        """Injeta o `IAudioClock` e o array `OSU_SCHEDULED_HIT_DTYPE`
        pre-carregado e ordenado (produzido por `OsuBeatmapLoader.load`).

        `on_hit_object_spawned` (opcional, default `None`): callback
        chamado UMA VEZ por hit-object disparado, como `(world,
        packed_entity_id, object_kind, x, y, end_x, end_y,
        duration_seconds, layer)`, DEPOIS que `osu_note_state` ja foi
        gravado. Este sistema deliberadamente NUNCA escreve em
        `transform`/`sprite` nem cria as entidades companheiras (anel de
        aproximacao / bola de slider) -- `on_hit_object_spawned` e o
        unico jeito do chamador fazer isso, incluindo escrever de volta
        `ring_entity_id`/`ball_entity_id` na propria linha de
        `osu_note_state` (re-resolvida via `unpack_index(packed_entity_id)`
        + `pool.dense_row_of(...)`, mesmo idioma de `_make_on_note_spawned`
        do modo lane).

        `hit_times`/`max_hits_per_frame`: mesmo contrato de
        `RhythmSpawnerSystem.__init__`.
        """
        self._audio_clock = audio_clock
        self._scheduled_hits = scheduled_hits
        self._hit_archetype_name = hit_archetype_name
        self._osu_note_state_pool_name = osu_note_state_pool_name
        self._max_hits_per_frame = max_hits_per_frame
        self._on_hit_object_spawned = on_hit_object_spawned
        self._hit_times = hit_times
        self._next_pending_index = 0

    @property
    def next_pending_index(self) -> int:
        """Indice do proximo evento ainda nao disparado (telemetria/testes deterministicos)."""
        return self._next_pending_index

    @property
    def is_finished(self) -> bool:
        """Verdadeiro quando `next_pending_index` alcancou o fim do array de eventos agendados."""
        return self._next_pending_index >= self._scheduled_hits.shape[0]

    def update(self, world: World, delta_time: float) -> None:
        """Dispara todos os hit-objects devidos desde a ultima chamada;
        `delta_time` e ignorado (ver docstring da classe)."""
        del delta_time  # deliberadamente ignorado -- ver docstring da classe

        if self.is_finished:
            return

        effective_time = self._compute_effective_time()
        due_count = self._count_due_events(effective_time)
        if due_count <= 0:
            return

        if self._max_hits_per_frame is not None:
            due_count = min(due_count, self._max_hits_per_frame)

        first_index = self._next_pending_index
        last_index = first_index + due_count
        self._spawn_due_events(world, first_index, last_index)
        self._next_pending_index = last_index

    def reset(self) -> None:
        """Reposiciona `self._next_pending_index` para 0."""
        self._next_pending_index = 0

    def _compute_effective_time(self) -> float:
        return max(0.0, self._audio_clock.now_seconds() - self._audio_clock.get_output_latency_seconds())

    def _count_due_events(self, effective_time: float) -> int:
        remaining_timestamps = self._scheduled_hits["timestamp_seconds"][self._next_pending_index :]
        if remaining_timestamps.shape[0] == 0:
            return 0
        return int(np.searchsorted(remaining_timestamps, effective_time, side="right"))

    def _spawn_due_events(self, world: World, first_index: int, last_index: int) -> None:
        for row_index in range(first_index, last_index):
            self._create_hit_entity(world, row_index)

    def _create_hit_entity(self, world: World, row_index: int) -> PackedEntityId:
        """Cria UM hit-object para a linha `row_index` de
        `self._scheduled_hits`, grava sua linha de `osu_note_state`, e
        invoca `on_hit_object_spawned` (se fornecido). Retorna o
        `PackedEntityId` bruto."""
        packed_entity_id = world.create_entity(self._hit_archetype_name)
        entity_index = unpack_index(packed_entity_id)

        note_state_pool = world.get_pool(self._osu_note_state_pool_name)
        note_state_row = note_state_pool.dense_row_of(entity_index)
        view = note_state_pool.active_view()

        scheduled_row = self._scheduled_hits[row_index]
        hit_time = self._hit_times[row_index] if self._hit_times is not None else scheduled_row["timestamp_seconds"]

        object_kind = int(scheduled_row["threat_type"])
        x = float(scheduled_row["x"])
        y = float(scheduled_row["y"])
        end_x = float(scheduled_row["end_x"])
        end_y = float(scheduled_row["end_y"])
        duration_seconds = float(scheduled_row["duration_seconds"])
        layer = int(scheduled_row["layer"])

        view["timestamp_seconds"][note_state_row] = hit_time
        view["packed_entity_id"][note_state_row] = packed_entity_id
        view["layer"][note_state_row] = layer
        view["object_kind"][note_state_row] = object_kind
        view["x"][note_state_row] = x
        view["y"][note_state_row] = y
        view["end_x"][note_state_row] = end_x
        view["end_y"][note_state_row] = end_y
        view["duration_seconds"][note_state_row] = duration_seconds
        # NULL_PACKED_HANDLE (nao 0!) -- ver docstring de OSU_NOTE_STATE_DTYPE:
        # um CIRCLE nunca tem ball_entity_id sobrescrito pelo callback, entao
        # este valor inicial e PERMANENTE para ele; precisa ser exatamente o
        # sentinela que OsuPresentationSystem mascara, nao um 0 arbitrario.
        view["ring_entity_id"][note_state_row] = NULL_PACKED_HANDLE
        view["ball_entity_id"][note_state_row] = NULL_PACKED_HANDLE
        view["is_tracking"][note_state_row] = False
        view["tracked_time_seconds"][note_state_row] = 0.0
        view["good_time_seconds"][note_state_row] = 0.0

        if self._on_hit_object_spawned is not None:
            self._on_hit_object_spawned(
                world, packed_entity_id, object_kind, x, y, end_x, end_y, duration_seconds, layer
            )

        return packed_entity_id
