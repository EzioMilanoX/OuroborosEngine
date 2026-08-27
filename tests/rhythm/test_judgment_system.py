# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Teste mais importante deste conjunto: JudgmentSystem deve julgar a
pressao do jogador exclusivamente a partir de IAudioClock.now_seconds()
(compensado por latencia), NUNCA a partir do delta_time acumulado --
mesmo criterio de RhythmSpawnerSystem/NoteScrollSystem. Cobre tambem os
thresholds Perfeito/Bom/Erro, expiracao por auto-erro, score/combo, e
que uma nota nunca e julgada duas vezes.
"""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.core.memory.handles import unpack_index
from ouroboros.rhythm.runtime.judgment_system import Judgment, JudgmentSystem
from ouroboros.rhythm.runtime.schemas import NOTE_STATE_DTYPE

LANE_POOL_NAME = "lane"
NOTE_STATE_POOL_NAME = "note_state"
ARCHETYPE_NAME = "note"
LANE_ACTIONS = ("lane_0", "lane_1", "lane_2", "lane_3")
# Precisa bater com DEFAULT_TEST_ENTITY_CAPACITY (tests/conftest.py): o array de
# scratch de JudgmentSystem e indexado por entity_index GLOBAL (administrado pelo
# MemoryManager por tras da fixture `memory_manager`), nao pela capacidade local de
# nenhuma pool -- um valor menor causa IndexError assim que o free-list do
# MemoryManager entrega um indice alto (ele desempilha do topo).
ENTITY_CAPACITY = 1024

PERFECT_WINDOW = 0.05
GOOD_WINDOW = 0.12
MISS_WINDOW = 0.20
POINTS = (300, 100, 0)


def _register_note_archetype(memory_manager, world):
    memory_manager.create_pool(LANE_POOL_NAME, np.dtype([("lane", np.int8)]))
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, NOTE_STATE_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, (LANE_POOL_NAME, NOTE_STATE_POOL_NAME))


def _spawn_note(world, lane: int, timestamp_seconds: float):
    packed = world.create_entity(ARCHETYPE_NAME)
    index = unpack_index(packed)
    lane_pool = world.get_pool(LANE_POOL_NAME)
    lane_pool.active_view()["lane"][lane_pool.dense_row_of(index)] = lane
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    row = note_state_pool.dense_row_of(index)
    note_state_pool.active_view()["timestamp_seconds"][row] = timestamp_seconds
    note_state_pool.active_view()["packed_entity_id"][row] = packed
    return packed


def _make_system(audio_clock, input_provider) -> JudgmentSystem:
    return JudgmentSystem(
        audio_clock=audio_clock,
        input_provider=input_provider,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        lane_pool_name=LANE_POOL_NAME,
        lane_action_names=LANE_ACTIONS,
        entity_capacity=ENTITY_CAPACITY,
        perfect_window_seconds=PERFECT_WINDOW,
        good_window_seconds=GOOD_WINDOW,
        miss_window_seconds=MISS_WINDOW,
        points_by_judgment=POINTS,
    )


def _update(system: JudgmentSystem, world, delta_time: float) -> None:
    """`system.update()` seguido de `world.flush()`: `world.destroy_entity()`
    e DIFERIDO ate `flush()` (normalmente chamado por `World.step()`) --
    chamar `update()` isolado, sem `step()`, exige o flush explicito aqui
    para o teste observar a remocao da nota julgada."""
    system.update(world, delta_time)
    world.flush()


def _press(input_provider, action_name: str) -> None:
    """Simula uma pressao de borda (`is_action_pressed` True neste frame)."""
    input_provider.set_action_held(action_name, True)
    input_provider.poll()


def _release_all(input_provider) -> None:
    for action in LANE_ACTIONS:
        input_provider.set_action_held(action, False)
    input_provider.poll()


def test_huge_delta_time_never_judges_anything_by_itself(memory_manager, world, null_audio_clock, null_input_provider):
    """(a) delta_time gigante, sem clock avancar e sem pressao -- nada e julgado. Prova que delta_time e ignorado."""
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(0.0)
    _update(system, world, 999.0)

    assert system.judged_count == 0
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 1


def test_press_exactly_on_time_is_perfect(memory_manager, world, null_audio_clock, null_input_provider):
    """(b) pressao exatamente no timestamp -> Perfeito, nota removida, score/combo atualizados."""
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.judged_count == 1
    assert system.score == POINTS[Judgment.PERFECT]
    assert system.combo == 1
    assert system.max_combo == 1
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 0


def test_press_within_good_window_but_outside_perfect_is_good(memory_manager, world, null_audio_clock, null_input_provider):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    delta = (PERFECT_WINDOW + GOOD_WINDOW) / 2.0  # entre as duas janelas
    null_audio_clock.set_now_seconds(1.0 + delta)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.score == POINTS[Judgment.GOOD]
    assert system.combo == 1


def test_press_within_miss_window_but_outside_good_is_a_manual_miss(memory_manager, world, null_audio_clock, null_input_provider):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    delta = (GOOD_WINDOW + MISS_WINDOW) / 2.0  # entre good e miss
    null_audio_clock.set_now_seconds(1.0 + delta)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.score == POINTS[Judgment.MISS]
    assert system.combo == 0
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 0  # ainda destruida, so que como Erro


def test_press_with_no_note_nearby_is_a_whiff_without_penalty(memory_manager, world, null_audio_clock, null_input_provider):
    """Lane vazia (ou nota fora da janela de miss): pressao nao penaliza nem julga nada (simplificacao documentada do v1)."""
    _register_note_archetype(memory_manager, world)
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.judged_count == 0
    assert system.score == 0
    assert system.combo == 0


def test_press_picks_nearest_note_in_the_correct_lane_only(memory_manager, world, null_audio_clock, null_input_provider):
    """Duas notas na mesma lane, AMBAS ainda dentro da janela de miss: a pressao deve julgar
    so a mais proxima do tempo atual, deixando a outra intocada (nao auto-errada nesta mesma
    chamada -- os timestamps sao escolhidos de propósito para nao expirar nenhuma delas)."""
    _register_note_archetype(memory_manager, world)
    packed_far = _spawn_note(world, lane=0, timestamp_seconds=1.40)  # diff = 0.08 de now=1.48
    packed_near = _spawn_note(world, lane=0, timestamp_seconds=1.50)  # diff = 0.02 de now=1.48
    _spawn_note(world, lane=1, timestamp_seconds=1.50)  # lane diferente -- nao deve ser afetada
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(1.48)  # mais perto de 1.50 do que de 1.40
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.judged_count == 1
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 2  # a de 1.40 e a de lane 1 continuam
    assert world.is_alive(packed_far)
    assert not world.is_alive(packed_near)


def test_note_expires_as_automatic_miss_without_any_press(memory_manager, world, null_audio_clock, null_input_provider):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    # ainda dentro da janela de miss -- nao deve expirar
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW - 0.01)
    _update(system, world, 0.016)
    assert system.judged_count == 0
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 1

    # passou da janela de miss sem pressao -> auto-erro
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)
    _update(system, world, 0.016)

    assert system.judged_count == 1
    assert system.score == POINTS[Judgment.MISS]
    assert system.combo == 0
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 0


def test_pressing_the_same_frame_a_note_expires_judges_it_only_once_via_press(
    memory_manager, world, null_audio_clock, null_input_provider
):
    """Nota dentro da janela de miss E pressionada no mesmo frame -- deve ser julgada pela pressao,
    nunca duplamente pelo passe de auto-erro (a mesma chamada de update() nao pode fazer as duas coisas)."""
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW - 0.001)  # dentro da janela por pouco
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert system.judged_count == 1  # nunca 2
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 0


def test_combo_resets_on_miss_and_max_combo_is_tracked(memory_manager, world, null_audio_clock, null_input_provider):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    _spawn_note(world, lane=0, timestamp_seconds=2.0)
    _spawn_note(world, lane=0, timestamp_seconds=3.0)
    system = _make_system(null_audio_clock, null_input_provider)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)
    assert system.combo == 1

    _release_all(null_input_provider)
    null_audio_clock.set_now_seconds(2.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)
    assert system.combo == 2
    assert system.max_combo == 2

    # a terceira nota expira sem pressao -> erro, zera o combo
    _release_all(null_input_provider)
    null_audio_clock.set_now_seconds(3.0 + MISS_WINDOW + 0.01)
    _update(system, world, 0.016)

    assert system.combo == 0
    assert system.max_combo == 2  # o pico alcancado antes do erro e preservado


SFX_IDS = ("sfx_perfect", "sfx_good", "sfx_miss")


def _make_system_with_audio(audio_clock, input_provider, audio_engine) -> JudgmentSystem:
    return JudgmentSystem(
        audio_clock=audio_clock,
        input_provider=input_provider,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        lane_pool_name=LANE_POOL_NAME,
        lane_action_names=LANE_ACTIONS,
        entity_capacity=ENTITY_CAPACITY,
        perfect_window_seconds=PERFECT_WINDOW,
        good_window_seconds=GOOD_WINDOW,
        miss_window_seconds=MISS_WINDOW,
        points_by_judgment=POINTS,
        audio_engine=audio_engine,
        sfx_ids_by_judgment=SFX_IDS,
    )


def test_perfect_judgment_plays_the_perfect_sfx_id(
    memory_manager, world, null_audio_clock, null_input_provider, null_audio_engine
):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system_with_audio(null_audio_clock, null_input_provider, null_audio_engine)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert null_audio_engine._one_shots_played == [(SFX_IDS[Judgment.PERFECT], 1.0)]


def test_good_judgment_plays_the_good_sfx_id(
    memory_manager, world, null_audio_clock, null_input_provider, null_audio_engine
):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system_with_audio(null_audio_clock, null_input_provider, null_audio_engine)

    delta = (PERFECT_WINDOW + GOOD_WINDOW) / 2.0
    null_audio_clock.set_now_seconds(1.0 + delta)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert null_audio_engine._one_shots_played == [(SFX_IDS[Judgment.GOOD], 1.0)]


def test_manual_miss_plays_the_miss_sfx_id(
    memory_manager, world, null_audio_clock, null_input_provider, null_audio_engine
):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system_with_audio(null_audio_clock, null_input_provider, null_audio_engine)

    delta = (GOOD_WINDOW + MISS_WINDOW) / 2.0
    null_audio_clock.set_now_seconds(1.0 + delta)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)

    assert null_audio_engine._one_shots_played == [(SFX_IDS[Judgment.MISS], 1.0)]


def test_auto_miss_plays_the_miss_sfx_id(
    memory_manager, world, null_audio_clock, null_input_provider, null_audio_engine
):
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system_with_audio(null_audio_clock, null_input_provider, null_audio_engine)

    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)
    _update(system, world, 0.016)

    assert null_audio_engine._one_shots_played == [(SFX_IDS[Judgment.MISS], 1.0)]


def test_whiff_and_untouched_notes_never_play_any_sfx(
    memory_manager, world, null_audio_clock, null_input_provider, null_audio_engine
):
    _register_note_archetype(memory_manager, world)
    system = _make_system_with_audio(null_audio_clock, null_input_provider, null_audio_engine)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")  # whiff: nenhuma nota nesta lane
    _update(system, world, 0.016)

    assert null_audio_engine._one_shots_played == []


def test_omitting_audio_engine_and_sfx_ids_preserves_old_behavior(memory_manager, world, null_audio_clock, null_input_provider):
    """Omitir os dois parametros (default None) nao levanta erro e nao tenta tocar nada."""
    _register_note_archetype(memory_manager, world)
    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    system = _make_system(null_audio_clock, null_input_provider)  # sem audio_engine/sfx_ids_by_judgment

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")
    _update(system, world, 0.016)  # nao deve levantar erro

    assert system.judged_count == 1


def test_sfx_ids_by_judgment_with_wrong_length_raises_at_construction(null_audio_clock, null_input_provider, null_audio_engine):
    with pytest.raises(ValueError):
        JudgmentSystem(
            audio_clock=null_audio_clock,
            input_provider=null_input_provider,
            note_state_pool_name=NOTE_STATE_POOL_NAME,
            lane_pool_name=LANE_POOL_NAME,
            lane_action_names=LANE_ACTIONS,
            entity_capacity=ENTITY_CAPACITY,
            audio_engine=null_audio_engine,
            sfx_ids_by_judgment=("only_two", "elements"),
        )


def test_accuracy_and_judged_count(memory_manager, world, null_audio_clock, null_input_provider):
    _register_note_archetype(memory_manager, world)
    system = _make_system(null_audio_clock, null_input_provider)
    assert system.accuracy == 1.0  # nada julgado ainda -- nao deve ser 0/0

    _spawn_note(world, lane=0, timestamp_seconds=1.0)
    _spawn_note(world, lane=1, timestamp_seconds=1.0)

    null_audio_clock.set_now_seconds(1.0)
    _press(null_input_provider, "lane_0")  # perfeito
    _update(system, world, 0.016)

    _release_all(null_input_provider)
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)  # lane_1 auto-erra
    _update(system, world, 0.016)

    assert system.judged_count == 2
    assert system.accuracy == pytest.approx(0.5)  # 1 acerto (perfeito+bom) em 2 julgados
