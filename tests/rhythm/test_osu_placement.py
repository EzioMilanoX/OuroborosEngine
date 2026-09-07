# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de place_hit_objects (ROADMAP M15): determinismo, espacamento, e o clamp de duracao de slider."""
from __future__ import annotations

import pytest

from ouroboros.rhythm.offline.osu_beatmap_schema import OSU_CIRCLE_THREAT_TYPE_NAME, OSU_SLIDER_THREAT_TYPE_NAME
from ouroboros.rhythm.offline.osu_placement import place_hit_objects

PLAYFIELD_WIDTH = 800.0
PLAYFIELD_HEIGHT = 600.0


def _threats(count: int, gap_seconds: float = 0.5) -> list:
    return [{"timestamp_seconds": i * gap_seconds, "strength": 0.0, "layer": ""} for i in range(count)]


def test_same_track_id_produces_the_same_layout_deterministically() -> None:
    threats = _threats(20)

    result_a = place_hit_objects(threats, "track_x", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT)
    result_b = place_hit_objects(threats, "track_x", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT)

    assert result_a == result_b


def test_different_track_ids_produce_different_layouts() -> None:
    threats = _threats(20)

    result_a = place_hit_objects(threats, "track_x", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT)
    result_b = place_hit_objects(threats, "track_y", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT)

    assert result_a != result_b


def test_produces_one_hit_object_per_threat_in_the_same_time_order() -> None:
    threats = _threats(10)
    hit_objects = place_hit_objects(threats, "t", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT)

    assert len(hit_objects) == 10
    assert [h.timestamp_seconds for h in hit_objects] == [t["timestamp_seconds"] for t in threats]


def test_every_nth_hit_object_is_a_slider() -> None:
    threats = _threats(12)
    hit_objects = place_hit_objects(
        threats, "t", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT, slider_every_n=4
    )

    kinds = [h.threat_type for h in hit_objects]
    assert kinds == [
        OSU_CIRCLE_THREAT_TYPE_NAME, OSU_CIRCLE_THREAT_TYPE_NAME, OSU_CIRCLE_THREAT_TYPE_NAME, OSU_SLIDER_THREAT_TYPE_NAME,
    ] * 3


def test_positions_stay_within_the_playfield_minus_margin() -> None:
    threats = _threats(30)
    hit_objects = place_hit_objects(
        threats, "t", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT, margin_px=60.0
    )

    for hit_object in hit_objects:
        assert 60.0 <= hit_object.x <= PLAYFIELD_WIDTH - 60.0
        assert 60.0 <= hit_object.y <= PLAYFIELD_HEIGHT - 60.0
        if hit_object.threat_type == OSU_SLIDER_THREAT_TYPE_NAME:
            assert 60.0 <= hit_object.end_x <= PLAYFIELD_WIDTH - 60.0
            assert 60.0 <= hit_object.end_y <= PLAYFIELD_HEIGHT - 60.0


def test_slider_duration_is_clamped_against_the_gap_to_the_next_onset() -> None:
    """Achado real da critica de M15: sem o clamp, uma duracao de 1
    batida inteira poderia ultrapassar um gap real MENOR entre onsets
    consecutivos (confirmado numericamente contra o beatmap real:
    ~0.488s/0.511s, mais curtos que 1 batida a 117bpm) -- a janela de
    julgamento do slider sobreporia a do proximo hit-object."""
    bpm = 120.0
    beat_seconds = 60.0 / bpm  # 0.5s
    short_gap_seconds = 0.3  # bem menor que 1 batida
    threats = [
        {"timestamp_seconds": 0.0, "strength": 0.0, "layer": ""},
        {"timestamp_seconds": 0.0 + short_gap_seconds, "strength": 0.0, "layer": ""},
        {"timestamp_seconds": 0.0 + short_gap_seconds + 1.0, "strength": 0.0, "layer": ""},
        {"timestamp_seconds": 0.0 + short_gap_seconds + 1.0 + 1.0, "strength": 0.0, "layer": ""},
    ]

    hit_objects = place_hit_objects(
        threats, "t", bpm=bpm, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT,
        slider_every_n=1, slider_safety_margin_seconds=0.05,
    )

    first_slider = hit_objects[0]
    assert first_slider.threat_type == OSU_SLIDER_THREAT_TYPE_NAME
    # duracao nominal seria 1 batida inteira (0.5s) -- deve ter sido
    # clampada pra caber antes do proximo onset (gap 0.3s) menos a margem de seguranca.
    assert first_slider.duration_seconds < beat_seconds
    assert first_slider.duration_seconds == pytest.approx(short_gap_seconds - 0.05)
    assert first_slider.timestamp_seconds + first_slider.duration_seconds < threats[1]["timestamp_seconds"]


def test_last_hit_object_slider_uses_the_nominal_duration_with_no_next_onset_to_clamp_against() -> None:
    bpm = 120.0
    beat_seconds = 60.0 / bpm
    threats = _threats(1)  # unico onset -- vira slider com slider_every_n=1

    hit_objects = place_hit_objects(
        threats, "t", bpm=bpm, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT, slider_every_n=1
    )

    assert hit_objects[0].duration_seconds == pytest.approx(beat_seconds)


def test_empty_threats_returns_empty_tuple() -> None:
    assert place_hit_objects([], "t", bpm=120.0, playfield_width=PLAYFIELD_WIDTH, playfield_height=PLAYFIELD_HEIGHT) == ()
