# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testes de OsuJudgmentSystem (ROADMAP M15). Cobre julgamento de circulo
por posicao+tempo, inicio/resolucao de tracking de slider (ponderado por
TEMPO REAL, nao contagem de frames -- achado real da critica de M15),
auto-erro de nunca-clicado (circulo E slider), e os dois bugs mais
criticos que a critica achou: reset imediato de `ring_entity_id` pra
`NULL_PACKED_HANDLE` no clique de um slider (evita handle obsoleto
reaproveitado por uma entidade nova), e destruicao de AMBAS as
companheiras (anel + bola) quando um slider nunca clicado e auto-errado
(evita vazamento de entidade orfa).
"""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.core.memory.handles import NULL_PACKED_HANDLE, unpack_index
from ouroboros.rhythm.runtime.judgment_system import Judgment
from ouroboros.rhythm.runtime.osu_judgment_system import OsuJudgmentSystem
from ouroboros.rhythm.runtime.schemas import OSU_NOTE_STATE_DTYPE, OsuObjectKind

NOTE_STATE_POOL_NAME = "osu_note_state"
NOTE_ARCHETYPE_NAME = "osu_note"
COMPANION_ARCHETYPE_NAME = "osu_visual_marker"

# Precisa bater com DEFAULT_TEST_ENTITY_CAPACITY (tests/conftest.py) --
# ver aviso identico em test_judgment_system.py.
ENTITY_CAPACITY = 1024

HIT_RADIUS = 20.0
SLIDER_FOLLOW_RADIUS = 25.0
PERFECT_WINDOW = 0.05
GOOD_WINDOW = 0.12
MISS_WINDOW = 0.20
SLIDER_PERFECT_FRACTION = 0.9
SLIDER_GOOD_FRACTION = 0.5
POINTS = (300, 100, 0)


def _register_archetypes(memory_manager, world):
    memory_manager.create_pool(NOTE_STATE_POOL_NAME, OSU_NOTE_STATE_DTYPE)
    world.register_archetype(NOTE_ARCHETYPE_NAME, (NOTE_STATE_POOL_NAME,))
    world.register_archetype(COMPANION_ARCHETYPE_NAME, ("transform",))


def _spawn_note(world, object_kind, timestamp_seconds, x=0.0, y=0.0, end_x=0.0, end_y=0.0, duration_seconds=0.0, layer=0):
    packed = world.create_entity(NOTE_ARCHETYPE_NAME)
    index = unpack_index(packed)
    note_state_pool = world.get_pool(NOTE_STATE_POOL_NAME)
    row = note_state_pool.dense_row_of(index)
    view = note_state_pool.active_view()
    view["timestamp_seconds"][row] = timestamp_seconds
    view["packed_entity_id"][row] = packed
    view["layer"][row] = layer
    view["object_kind"][row] = object_kind
    view["x"][row] = x
    view["y"][row] = y
    view["end_x"][row] = end_x
    view["end_y"][row] = end_y
    view["duration_seconds"][row] = duration_seconds
    view["ring_entity_id"][row] = NULL_PACKED_HANDLE
    view["ball_entity_id"][row] = NULL_PACKED_HANDLE
    view["is_tracking"][row] = False
    return packed, row


def _attach_companion(world, note_row, field_name: str):
    packed = world.create_entity(COMPANION_ARCHETYPE_NAME)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()[field_name][note_row] = packed
    return packed


def _make_system(audio_clock, input_provider, on_judgment=None) -> OsuJudgmentSystem:
    return OsuJudgmentSystem(
        audio_clock=audio_clock,
        input_provider=input_provider,
        note_state_pool_name=NOTE_STATE_POOL_NAME,
        entity_capacity=ENTITY_CAPACITY,
        hit_radius_px=HIT_RADIUS,
        slider_follow_radius_px=SLIDER_FOLLOW_RADIUS,
        perfect_window_seconds=PERFECT_WINDOW,
        good_window_seconds=GOOD_WINDOW,
        miss_window_seconds=MISS_WINDOW,
        slider_perfect_fraction=SLIDER_PERFECT_FRACTION,
        slider_good_fraction=SLIDER_GOOD_FRACTION,
        points_by_judgment=POINTS,
        on_judgment=on_judgment,
    )


def _update(system, world, delta_time=0.016):
    system.update(world, delta_time)
    world.flush()


def _click(input_provider):
    input_provider.set_action_held("click", True)
    input_provider.poll()


def _release(input_provider):
    input_provider.set_action_held("click", False)
    input_provider.poll()


# ---------------------------------------------------------------------
# Circulo: julgamento por posicao + tempo
# ---------------------------------------------------------------------


def test_clicking_a_circle_within_radius_and_perfect_window_scores_perfect(memory_manager, world, null_audio_clock, null_input_provider):
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=100.0, y=100.0)
    ring_packed = _attach_companion(world, row, "ring_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(105.0, 100.0)  # dentro do raio
    _click(null_input_provider)

    _update(system, world)

    assert system.score == POINTS[Judgment.PERFECT]
    assert not world.is_alive(packed)
    assert not world.is_alive(ring_packed)


def test_clicking_outside_hit_radius_is_a_whiff_without_penalty(memory_manager, world, null_audio_clock, null_input_provider):
    _register_archetypes(memory_manager, world)
    _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=100.0, y=100.0)

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(100.0 + HIT_RADIUS + 50.0, 100.0)  # bem fora do raio
    _click(null_input_provider)

    _update(system, world)

    assert system.score == 0
    assert system.judged_count == 0
    assert world.get_pool(NOTE_STATE_POOL_NAME).count == 1  # nada foi julgado ainda


def test_on_judgment_callback_receives_the_objects_real_position(memory_manager, world, null_audio_clock, null_input_provider):
    calls = []
    system = _make_system(
        null_audio_clock, null_input_provider,
        on_judgment=lambda judgment, layer, x, y: calls.append((judgment, layer, x, y)),
    )
    _register_archetypes(memory_manager, world)
    _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=42.0, y=84.0, layer=1)

    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(42.0, 84.0)
    _click(null_input_provider)
    _update(system, world)

    assert calls == [(Judgment.PERFECT, 1, 42.0, 84.0)]


# ---------------------------------------------------------------------
# Slider: inicio de tracking, reset imediato do handle do anel
# ---------------------------------------------------------------------


def test_clicking_a_slider_starts_tracking_and_resets_ring_handle_immediately(memory_manager, world, null_audio_clock, null_input_provider):
    """Achado real da critica de M15: sem o reset imediato pra
    NULL_PACKED_HANDLE, este campo manteria um handle obsoleto,
    rapidamente reaproveitado (MemoryManager e LIFO) por uma entidade
    NOVA e nao-relacionada -- um leitor vetorizado escreveria na
    entidade errada."""
    _register_archetypes(memory_manager, world)
    _, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=100.0, y=100.0, end_x=200.0, end_y=100.0, duration_seconds=1.0)
    ring_packed = _attach_companion(world, row, "ring_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(100.0, 100.0)
    _click(null_input_provider)

    _update(system, world)

    note_state_view = world.get_pool(NOTE_STATE_POOL_NAME).active_view()
    assert bool(note_state_view["is_tracking"][row]) is True
    assert int(note_state_view["ring_entity_id"][row]) == NULL_PACKED_HANDLE
    assert not world.is_alive(ring_packed)
    assert system.judged_count == 0  # ainda nao julgado -- so a cabeca+bola resolvem isso depois


def test_ring_handle_reset_prevents_cross_contamination_after_index_reuse(memory_manager, world, null_audio_clock, null_input_provider):
    """Regressao direta e mais forte: depois do clique no slider (anel
    destruido+anulado), forca uma NOVA entidade companheira a reaproveitar
    o MESMO indice global (MemoryManager libera em LIFO) e confirma que
    OsuPresentationSystem NUNCA escreve no transform dela por causa do
    campo obsoleto do slider original."""
    from ouroboros.rhythm.runtime.osu_presentation_system import OsuPresentationSystem

    _register_archetypes(memory_manager, world)
    _, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=100.0, y=100.0, end_x=200.0, end_y=100.0, duration_seconds=1.0)
    ring_packed = _attach_companion(world, row, "ring_entity_id")
    freed_index = unpack_index(ring_packed)

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(100.0, 100.0)
    _click(null_input_provider)
    _update(system, world)  # destroi o anel, zera ring_entity_id, e faz flush (libera o indice)

    # Uma entidade nova e nao-relacionada reaproveita o MESMO indice global
    # (LIFO) -- marca seu transform com um valor sentinela pra detectar
    # qualquer escrita indevida.
    new_packed = world.create_entity(COMPANION_ARCHETYPE_NAME)
    assert unpack_index(new_packed) == freed_index, "premissa do teste: MemoryManager deve reaproveitar o indice em LIFO"
    transform_pool = world.get_pool("transform")
    new_row = transform_pool.dense_row_of(freed_index)
    transform_pool.active_view()["scale_x"][new_row] = 999.0

    presentation = OsuPresentationSystem(
        audio_clock=null_audio_clock, note_state_pool_name=NOTE_STATE_POOL_NAME,
        transform_pool_name="transform", approach_seconds=1.0, ring_start_scale=3.0,
    )
    presentation.update(world, delta_time=0.016)  # nao deve levantar erro nem tocar a entidade nova

    assert float(transform_pool.active_view()["scale_x"][new_row]) == 999.0


# ---------------------------------------------------------------------
# Slider: tracking ponderado por TEMPO REAL, nao contagem de frames
# ---------------------------------------------------------------------


def test_slider_tracking_fraction_is_invariant_to_frame_rate(memory_manager, world, null_audio_clock, null_input_provider):
    """Achado real da critica de M15: ponderar por CONTAGEM DE FRAMES em
    vez de tempo real enviesaria a fracao pela taxa de quadros. Aqui, o
    MESMO comportamento fisico (cursor dentro do raio por METADE do
    tempo real total) deve produzir a MESMA fracao final, seja com
    poucos frames grandes ou muitos frames pequenos."""
    _register_archetypes(memory_manager, world)
    _, row_many_frames = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=0.0, end_y=0.0, duration_seconds=1.0)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()["is_tracking"][row_many_frames] = True

    system = _make_system(null_audio_clock, null_input_provider)
    null_input_provider.set_cursor_position(0.0, 0.0)  # sempre dentro do raio (slider parado em (0,0))

    # Metade do tempo (0.5s de 1.0s total) com botao solto, metade com botao
    # pressionado -- simulado em 100 frames pequenos (~0.01s cada).
    total_frames = 100
    for i in range(total_frames):
        if i < total_frames // 2:
            _release(null_input_provider)
        else:
            _click(null_input_provider)
        null_audio_clock.set_now_seconds(1.0 + (i + 1) * (1.0 / total_frames))
        system.update(world, delta_time=1.0 / total_frames)

    view = world.get_pool(NOTE_STATE_POOL_NAME).active_view()
    tracked = float(view["tracked_time_seconds"][row_many_frames])
    good = float(view["good_time_seconds"][row_many_frames])
    fraction_many_frames = good / tracked

    assert fraction_many_frames == pytest.approx(0.5, abs=0.02)


def test_slider_tracking_uses_delta_time_not_frame_count_directly(memory_manager, world, null_audio_clock, null_input_provider):
    """Mais direto: 1 frame GIGANTE (delta_time=0.5s, dentro do raio) deve
    contar tanto quanto 50 frames pequenos de 0.01s cada (dentro do raio)
    -- se o acumulador fosse por CONTAGEM DE FRAMES, o frame gigante
    contaria como '1 frame bom' igual a cada frame pequeno, inflando a
    fracao de forma incorreta."""
    _register_archetypes(memory_manager, world)
    _, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=0.0, end_y=0.0, duration_seconds=10.0)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()["is_tracking"][row] = True

    system = _make_system(null_audio_clock, null_input_provider)
    null_input_provider.set_cursor_position(0.0, 0.0)
    _click(null_input_provider)

    null_audio_clock.set_now_seconds(1.5)
    system.update(world, delta_time=0.5)  # 1 frame gigante de 0.5s

    view = world.get_pool(NOTE_STATE_POOL_NAME).active_view()
    assert float(view["tracked_time_seconds"][row]) == pytest.approx(0.5)
    assert float(view["good_time_seconds"][row]) == pytest.approx(0.5)


# ---------------------------------------------------------------------
# Resolucao de slider ao fim da duracao
# ---------------------------------------------------------------------


def test_slider_resolves_perfect_when_tracked_well_the_whole_duration(memory_manager, world, null_audio_clock, null_input_provider):
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=100.0, end_y=0.0, duration_seconds=1.0)
    ball_packed = _attach_companion(world, row, "ball_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(0.0, 0.0)
    _click(null_input_provider)
    _update(system, world)  # inicia tracking

    # Fracoes calculadas cada uma do zero (nunca por soma acumulada em
    # ponto flutuante -- `1.0 + 0.2*5` NAO bate exatamente com `2.0` por
    # erro de arredondamento de `0.2`, o que deixaria o slider "quase"
    # resolvido mas nao o bastante para `elapsed >= duration_seconds`).
    for step in range(1, 6):
        fraction = step / 5.0
        null_audio_clock.set_now_seconds(1.0 + fraction * 1.0)
        null_input_provider.set_cursor_position(fraction * 100.0, 0.0)
        _click(null_input_provider)  # mantem o botao "segurado" (is_action_held) a cada passo
        _update(system, world)

    assert system.judged_count == 1
    assert system.score == POINTS[Judgment.PERFECT]
    assert not world.is_alive(packed)
    assert not world.is_alive(ball_packed)


def test_slider_resolves_miss_when_never_tracked_well(memory_manager, world, null_audio_clock, null_input_provider):
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=100.0, end_y=0.0, duration_seconds=1.0)
    _attach_companion(world, row, "ball_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0)
    null_input_provider.set_cursor_position(0.0, 0.0)
    _click(null_input_provider)
    _update(system, world)  # inicia tracking -- o proprio instante do clique conta como "bom" (cursor == cabeca)

    # Muitos frames com o botao solto (cursor nunca acompanha) ANTES do fim
    # da duracao -- dilui o instante inicial "bom" ate a fracao cair bem
    # abaixo do limiar de Bom, sem depender de um valor exato de fronteira.
    _release(null_input_provider)
    for step in range(1, 21):
        null_audio_clock.set_now_seconds(1.0 + (step / 20.0) * 1.0)
        _update(system, world)

    assert system.judged_count == 1
    assert system.score == POINTS[Judgment.MISS]
    assert not world.is_alive(packed)


# ---------------------------------------------------------------------
# Auto-erro de objetos nunca clicados -- destroi TODAS as companheiras vivas
# ---------------------------------------------------------------------


def test_auto_miss_never_clicked_circle_destroys_head_and_ring(memory_manager, world, null_audio_clock, null_input_provider):
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.CIRCLE, timestamp_seconds=1.0, x=0.0, y=0.0)
    ring_packed = _attach_companion(world, row, "ring_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)
    _update(system, world)

    assert system.score == POINTS[Judgment.MISS]
    assert not world.is_alive(packed)
    assert not world.is_alive(ring_packed)


def test_auto_miss_never_clicked_slider_destroys_head_ring_and_ball(memory_manager, world, null_audio_clock, null_input_provider):
    """Achado real da critica de M15: um slider NUNCA clicado ainda tem
    AMBAS as companheiras vivas (diferente de um slider clicado, cujo
    anel ja foi destruido) -- as duas precisam ser destruidas aqui, ou
    a bola vaza como entidade orfa permanente."""
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=10.0, end_y=10.0, duration_seconds=1.0)
    ring_packed = _attach_companion(world, row, "ring_entity_id")
    ball_packed = _attach_companion(world, row, "ball_entity_id")

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)
    _update(system, world)

    assert system.score == POINTS[Judgment.MISS]
    assert not world.is_alive(packed)
    assert not world.is_alive(ring_packed)
    assert not world.is_alive(ball_packed), "bola de slider nunca clicado nao pode vazar como entidade orfa"


def test_slider_currently_tracking_is_never_auto_missed(memory_manager, world, null_audio_clock, null_input_provider):
    """Um slider em tracking ja passou, necessariamente, do instante da
    cabeca -- nao pode ser confundido com 'nunca clicado vencido'."""
    _register_archetypes(memory_manager, world)
    packed, row = _spawn_note(world, OsuObjectKind.SLIDER, timestamp_seconds=1.0, x=0.0, y=0.0, end_x=10.0, end_y=10.0, duration_seconds=2.0)
    world.get_pool(NOTE_STATE_POOL_NAME).active_view()["is_tracking"][row] = True

    system = _make_system(null_audio_clock, null_input_provider)
    null_audio_clock.set_now_seconds(1.0 + MISS_WINDOW + 0.01)  # bem alem da janela de erro da CABECA
    _update(system, world)

    assert system.judged_count == 0
    assert world.is_alive(packed)
