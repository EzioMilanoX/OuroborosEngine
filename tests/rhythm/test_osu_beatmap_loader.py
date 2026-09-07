# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de OsuBeatmapLoader (ROADMAP M15): carga real do beatmap gerado + validacao de malformados."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.rhythm.runtime.beatmap_loader import BeatmapFormatError
from ouroboros.rhythm.runtime.osu_beatmap_loader import OsuBeatmapLoader
from ouroboros.rhythm.runtime.schemas import OsuObjectKind

_REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_OSU_BEATMAP_PATH = _REPO_ROOT / "data" / "beatmaps" / "demo_track_osu.beatmap.json"

_TYPE_MAP = {"osu_circle": int(OsuObjectKind.CIRCLE), "osu_slider": int(OsuObjectKind.SLIDER)}


def _loader() -> OsuBeatmapLoader:
    return OsuBeatmapLoader(threat_type_name_to_id=_TYPE_MAP, slider_threat_type_id=int(OsuObjectKind.SLIDER))


def test_load_reads_the_real_generated_beatmap() -> None:
    scheduled_hits = _loader().load(REAL_OSU_BEATMAP_PATH)

    assert scheduled_hits.shape[0] == 39
    assert (scheduled_hits["timestamp_seconds"][:-1] <= scheduled_hits["timestamp_seconds"][1:]).all()
    slider_mask = scheduled_hits["threat_type"] == int(OsuObjectKind.SLIDER)
    assert slider_mask.sum() == 9
    assert (scheduled_hits["duration_seconds"][slider_mask] > 0.0).all()
    circle_mask = ~slider_mask
    assert (scheduled_hits["duration_seconds"][circle_mask] == 0.0).all()


def _write(tmp_path: Path, threats: list, bpm: float = 120.0) -> Path:
    path = tmp_path / "test.beatmap.json"
    path.write_text(
        json.dumps({"version": 1, "track_id": "test", "bpm": bpm, "threats": threats}), encoding="utf-8"
    )
    return path


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"timestamp_seconds": 1.0, "threat_type": "osu_circle", "x": 10.0, "strength": 0.5}])
    with pytest.raises(BeatmapFormatError):
        _loader().load(path)


def test_unknown_threat_type_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path, [{"timestamp_seconds": 1.0, "threat_type": "unknown", "x": 10.0, "y": 20.0, "strength": 0.5}]
    )
    with pytest.raises(BeatmapFormatError):
        _loader().load(path)


def test_slider_missing_end_x_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "timestamp_seconds": 1.0, "threat_type": "osu_slider", "x": 10.0, "y": 20.0, "strength": 0.5,
                "end_y": 30.0, "duration_seconds": 0.5,
            }
        ],
    )
    with pytest.raises(BeatmapFormatError):
        _loader().load(path)


def test_circle_never_requires_slider_fields(tmp_path: Path) -> None:
    path = _write(
        tmp_path, [{"timestamp_seconds": 1.0, "threat_type": "osu_circle", "x": 10.0, "y": 20.0, "strength": 0.5}]
    )
    scheduled_hits = _loader().load(path)
    assert scheduled_hits.shape[0] == 1
    assert scheduled_hits[0]["duration_seconds"] == 0.0
