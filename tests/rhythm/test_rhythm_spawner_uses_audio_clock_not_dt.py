# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Teste mais importante do Pilar 4: RhythmSpawnerSystem deve decidir O QUE
disparar exclusivamente a partir de `IAudioClock.now_seconds()` (compensado
pela latencia de saida), NUNCA a partir do `delta_time` acumulado recebido
por `update()`. Tambem exercita o mecanismo de cursor pre-alocado
(`_next_pending_index` via `np.searchsorted`), a idempotencia sem `set()`/
`dict`, a compensacao de `calibrate_latency`, e `reset()`.
"""
from __future__ import annotations

import numpy as np

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.rhythm.runtime.rhythm_spawner_system import RhythmSpawnerSystem
from ouroboros.rhythm.runtime.schemas import NOTE_STATE_DTYPE, SCHEDULED_THREAT_DTYPE

LANE_POOL_NAME = "lane"
THREAT_TYPE_POOL_NAME = "threat_type"
ARCHETYPE_NAME = "threat"


def _build_scheduled_threats() -> np.ndarray:
    timestamps = [1.0, 2.0, 3.0, 5.0]
    lanes = [0, 1, 2, 3]
    threat_types = [0, 1, 0, 1]
    strengths = [0.1, 0.2, 0.3, 0.4]

    scheduled = np.zeros(len(timestamps), dtype=SCHEDULED_THREAT_DTYPE)
    scheduled["timestamp_seconds"] = timestamps
    scheduled["lane"] = lanes
    scheduled["threat_type"] = threat_types
    scheduled["strength"] = strengths
    scheduled["has_spawned"] = False
    return scheduled


def _register_threat_archetype(memory_manager: MemoryManager, world: World) -> None:
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME))


def _make_system(audio_clock: IAudioClock, scheduled_threats: np.ndarray) -> RhythmSpawnerSystem:
    return RhythmSpawnerSystem(
        audio_clock=audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        max_threats_per_frame=None,
    )


def test_full_lifecycle_uses_audio_clock_not_delta_time(memory_manager, world, null_audio_clock):
    _register_threat_archetype(memory_manager, world)
    scheduled_threats = _build_scheduled_threats()
    system = _make_system(null_audio_clock, scheduled_threats)

    lane_pool = world.get_pool(LANE_POOL_NAME)
    threat_type_pool = world.get_pool(THREAT_TYPE_POOL_NAME)

    # ------------------------------------------------------------------
    # (a) Clock parado em now_seconds() == 0: mesmo um delta_time gigante
    # NAO deve disparar nada -- prova que delta_time e ignorado.
    # ------------------------------------------------------------------
    system.update(world, delta_time=999.0)
    assert system.next_pending_index == 0
    assert lane_pool.count == 0
    assert threat_type_pool.count == 0

    # ------------------------------------------------------------------
    # (b) Avancar o clock alem do timestamp do primeiro evento (1.0s)
    # dispara exatamente esse evento.
    # ------------------------------------------------------------------
    null_audio_clock.advance(1.2)  # now_seconds() == 1.2
    system.update(world, delta_time=0.016)

    assert system.next_pending_index == 1
    assert lane_pool.count == 1
    assert threat_type_pool.count == 1
    assert int(lane_pool.active_view()["lane"][0]) == 0
    assert int(threat_type_pool.active_view()["threat_type"][0]) == 0

    # ------------------------------------------------------------------
    # (c) Chamar update() de novo SEM avancar o clock nao dispara o mesmo
    # evento outra vez (idempotencia via cursor, sem set()/dict).
    # ------------------------------------------------------------------
    system.update(world, delta_time=0.016)
    assert system.next_pending_index == 1
    assert lane_pool.count == 1
    assert threat_type_pool.count == 1

    # ------------------------------------------------------------------
    # (d) calibrate_latency desloca efetivamente quando os eventos disparam.
    # now=2.0 com latencia 0.5 -> effective_time=1.5 < 2.0 (timestamp do
    # segundo evento): NAO deve disparar ainda.
    # ------------------------------------------------------------------
    null_audio_clock.set_now_seconds(2.0)
    null_audio_clock.calibrate_latency(0.5)
    system.update(world, delta_time=0.016)

    assert system.next_pending_index == 1, "compensacao de latencia deveria atrasar o disparo"
    assert lane_pool.count == 1

    # Avancando now_seconds() o suficiente para que now - latencia >= 2.0
    # finalmente dispara o segundo evento (e apenas ele: terceiro evento
    # esta em 3.0s, effective_time aqui e 2.1s).
    null_audio_clock.set_now_seconds(2.6)
    system.update(world, delta_time=0.016)

    assert system.next_pending_index == 2
    assert lane_pool.count == 2
    assert threat_type_pool.count == 2
    assert int(lane_pool.active_view()["lane"][1]) == 1
    assert int(threat_type_pool.active_view()["threat_type"][1]) == 1

    # ------------------------------------------------------------------
    # (e) reset() volta o cursor para reprocessar do inicio.
    # ------------------------------------------------------------------
    system.reset()
    assert system.next_pending_index == 0

    # now_seconds() ainda em 2.6, latencia ainda 0.5 -> effective_time=2.1:
    # eventos 0 (1.0s) e 1 (2.0s) voltam a ser considerados "devidos" a
    # partir do cursor reiniciado, e novas entidades sao criadas para eles
    # (reset() rebobina apenas o cursor -- nao desfaz entidades ja criadas).
    system.update(world, delta_time=0.016)

    assert system.next_pending_index == 2
    assert lane_pool.count == 4
    assert threat_type_pool.count == 4


def test_max_threats_per_frame_throttles_without_dropping_events(memory_manager, world, null_audio_clock):
    _register_threat_archetype(memory_manager, world)
    scheduled_threats = _build_scheduled_threats()
    system = RhythmSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        max_threats_per_frame=1,
    )

    lane_pool = world.get_pool(LANE_POOL_NAME)

    # Avanca o clock alem de TODOS os 4 timestamps de uma vez (simula o
    # jogo tendo ficado pausado/atrasado); com max_threats_per_frame=1, cada
    # update() so deve disparar 1 evento por vez, sem descartar nenhum.
    null_audio_clock.set_now_seconds(10.0)

    for expected_count in (1, 2, 3, 4):
        system.update(world, delta_time=0.016)
        assert system.next_pending_index == expected_count
        assert lane_pool.count == expected_count

    assert system.is_finished

    # Chamadas adicionais depois de terminado sao no-ops seguros.
    system.update(world, delta_time=0.016)
    assert system.next_pending_index == 4
    assert lane_pool.count == 4


def test_is_finished_property_reflects_cursor_position(memory_manager, world, null_audio_clock):
    _register_threat_archetype(memory_manager, world)
    scheduled_threats = _build_scheduled_threats()
    system = _make_system(null_audio_clock, scheduled_threats)

    assert not system.is_finished

    null_audio_clock.set_now_seconds(100.0)
    system.update(world, delta_time=0.016)

    assert system.is_finished
    assert system.next_pending_index == scheduled_threats.shape[0]


def test_empty_scheduled_threats_is_immediately_finished(memory_manager, world, null_audio_clock):
    _register_threat_archetype(memory_manager, world)
    empty_scheduled_threats = np.zeros(0, dtype=SCHEDULED_THREAT_DTYPE)
    system = _make_system(null_audio_clock, empty_scheduled_threats)

    assert system.is_finished

    null_audio_clock.set_now_seconds(50.0)
    system.update(world, delta_time=0.016)  # nao deve levantar erro

    assert system.next_pending_index == 0
    assert world.get_pool(LANE_POOL_NAME).count == 0


NOTE_STATE_POOL_NAME = "note_state"


def test_note_state_pool_name_writes_timestamp_and_packed_id(memory_manager, world, null_audio_clock):
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME, NOTE_STATE_POOL_NAME))

    scheduled_threats = _build_scheduled_threats()
    system = RhythmSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
    )

    null_audio_clock.advance(1.2)  # dispara o primeiro evento (timestamp 1.0)
    system.update(world, delta_time=0.016)

    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    assert note_state_pool.count == 1
    row = note_state_pool.active_view()[0]
    assert float(row["timestamp_seconds"]) == 1.0

    lane_pool = world.get_pool(LANE_POOL_NAME)
    spawned_entity_index = lane_pool.active_entity_indices()[0]
    assert unpack_index(int(row["packed_entity_id"])) == spawned_entity_index


def test_note_state_pool_name_omitted_leaves_pool_untouched(memory_manager, world, null_audio_clock):
    """Comportamento antigo (sem `note_state_pool_name`) continua identico -- nenhuma pool extra e tocada."""
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME))

    scheduled_threats = _build_scheduled_threats()
    system = _make_system(null_audio_clock, scheduled_threats)

    null_audio_clock.advance(1.2)
    system.update(world, delta_time=0.016)  # nao deve levantar erro por falta de note_state_pool_name

    assert world.get_pool(LANE_POOL_NAME).count == 1


def test_hit_times_overrides_timestamp_written_to_note_state(memory_manager, world, null_audio_clock):
    """Quando `hit_times` e fornecido, `note_state` grava o tempo de ACERTO
    real (nao o timestamp de spawn de `scheduled_threats`) -- prova de que
    a separacao spawn-cue vs hit-time funciona."""
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME, NOTE_STATE_POOL_NAME))

    # scheduled_threats carrega os tempos de SPAWN (ja deslocados); hit_times
    # carrega os tempos de ACERTO reais, paralelos linha a linha.
    scheduled_threats = _build_scheduled_threats()  # timestamps de spawn: 1.0, 2.0, 3.0, 5.0
    hit_times = np.array([2.5, 3.5, 4.5, 6.5], dtype=np.float64)  # tempos de acerto reais
    system = RhythmSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        hit_times=hit_times,
    )

    null_audio_clock.advance(1.2)  # dispara o primeiro evento (timestamp de spawn 1.0)
    system.update(world, delta_time=0.016)

    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    assert note_state_pool.count == 1
    row = note_state_pool.active_view()[0]
    assert float(row["timestamp_seconds"]) == 2.5, "deve gravar o hit_time real, nao o timestamp de spawn"


def test_hit_times_omitted_preserves_old_behavior(memory_manager, world, null_audio_clock):
    """Sem `hit_times` (default None), `note_state` continua gravando o
    proprio `timestamp_seconds` de `scheduled_threats` -- comportamento
    antigo, identico a `test_note_state_pool_name_writes_timestamp_and_packed_id`."""
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME, NOTE_STATE_POOL_NAME))

    scheduled_threats = _build_scheduled_threats()
    system = RhythmSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
    )

    null_audio_clock.advance(1.2)
    system.update(world, delta_time=0.016)

    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    row = note_state_pool.active_view()[0]
    assert float(row["timestamp_seconds"]) == 1.0


def test_on_note_spawned_callback_receives_world_packed_id_lane_and_threat_type(memory_manager, world, null_audio_clock):
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(THREAT_TYPE_POOL_NAME, np.dtype([("threat_type", np.int16)]))
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, THREAT_TYPE_POOL_NAME))

    calls = []

    def on_note_spawned(callback_world, packed_entity_id, lane, threat_type):
        calls.append((callback_world, packed_entity_id, lane, threat_type))

    scheduled_threats = _build_scheduled_threats()
    system = RhythmSpawnerSystem(
        audio_clock=null_audio_clock,
        scheduled_threats=scheduled_threats,
        threat_archetype_name=ARCHETYPE_NAME,
        lane_pool_name=LANE_POOL_NAME,
        threat_type_pool_name=THREAT_TYPE_POOL_NAME,
        on_note_spawned=on_note_spawned,
    )

    null_audio_clock.advance(1.2)  # dispara evento 0: lane=0, threat_type=0
    system.update(world, delta_time=0.016)

    assert len(calls) == 1
    callback_world, packed_entity_id, lane, threat_type = calls[0]
    assert callback_world is world
    assert world.is_alive(packed_entity_id)
    assert lane == 0
    assert threat_type == 0

    null_audio_clock.set_now_seconds(2.6)  # dispara evento 1: lane=1, threat_type=1
    system.update(world, delta_time=0.016)

    assert len(calls) == 2
    assert calls[1][2:] == (1, 1)
