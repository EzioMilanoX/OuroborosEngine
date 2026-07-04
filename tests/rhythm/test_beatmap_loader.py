"""Testa BeatmapLoader (runtime): parsing, ordenacao e mapeamento threat_type -> int."""
from __future__ import annotations

import json

import numpy as np
import pytest

from ouroboros.rhythm.beatmap_format import BEATMAP_SCHEMA_VERSION
from ouroboros.rhythm.runtime.beatmap_loader import BeatmapFormatError, BeatmapLoader
from ouroboros.rhythm.runtime.schemas import SCHEDULED_THREAT_DTYPE


def _write_beatmap(path, beatmap_dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(beatmap_dict, f)


def _hand_written_beatmap_dict():
    return {
        "version": BEATMAP_SCHEMA_VERSION,
        "track_id": "hand_written_track",
        "bpm": 90.0,
        "threats": [
            {"timestamp_seconds": 2.0, "threat_type": "rhythm_threat_basic", "lane": 1, "strength": 0.5},
            {"timestamp_seconds": 0.5, "threat_type": "rhythm_threat_heavy", "lane": 0, "strength": 0.9},
            {"timestamp_seconds": 1.0, "threat_type": "rhythm_threat_basic", "lane": 2, "strength": 0.1},
        ],
    }


def test_load_returns_array_sorted_by_timestamp_with_dtype(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    _write_beatmap(beatmap_path, _hand_written_beatmap_dict())

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    scheduled = loader.load(beatmap_path)

    assert scheduled.dtype == SCHEDULED_THREAT_DTYPE
    assert scheduled.shape[0] == 3

    timestamps = scheduled["timestamp_seconds"]
    assert (timestamps[:-1] <= timestamps[1:]).all()
    assert list(timestamps) == [0.5, 1.0, 2.0]


def test_load_maps_threat_type_string_to_int(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    _write_beatmap(beatmap_path, _hand_written_beatmap_dict())

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    scheduled = loader.load(beatmap_path)

    # apos ordenar por timestamp: 0.5s -> heavy(1), 1.0s -> basic(0), 2.0s -> basic(0)
    assert list(scheduled["threat_type"]) == [1, 0, 0]
    assert list(scheduled["lane"]) == [0, 2, 1]


def test_load_sets_has_spawned_false_for_all_rows(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    _write_beatmap(beatmap_path, _hand_written_beatmap_dict())

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    scheduled = loader.load(beatmap_path)

    assert not scheduled["has_spawned"].any()


def test_load_unknown_schema_version_raises_beatmap_format_error(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    beatmap_dict = _hand_written_beatmap_dict()
    beatmap_dict["version"] = BEATMAP_SCHEMA_VERSION + 777
    _write_beatmap(beatmap_path, beatmap_dict)

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    with pytest.raises(BeatmapFormatError):
        loader.load(beatmap_path)


def test_load_unknown_threat_type_raises_beatmap_format_error(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    beatmap_dict = _hand_written_beatmap_dict()
    _write_beatmap(beatmap_path, beatmap_dict)

    loader = BeatmapLoader({"rhythm_threat_basic": 0})  # falta "rhythm_threat_heavy"
    with pytest.raises(BeatmapFormatError):
        loader.load(beatmap_path)


def test_load_missing_required_field_raises_beatmap_format_error(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    beatmap_dict = _hand_written_beatmap_dict()
    del beatmap_dict["bpm"]
    _write_beatmap(beatmap_path, beatmap_dict)

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    with pytest.raises(BeatmapFormatError):
        loader.load(beatmap_path)


def test_load_empty_threats_returns_empty_array(tmp_path):
    beatmap_path = tmp_path / "beatmap.json"
    beatmap_dict = _hand_written_beatmap_dict()
    beatmap_dict["threats"] = []
    _write_beatmap(beatmap_path, beatmap_dict)

    loader = BeatmapLoader({"rhythm_threat_basic": 0, "rhythm_threat_heavy": 1})
    scheduled = loader.load(beatmap_path)

    assert scheduled.shape[0] == 0
    assert scheduled.dtype == SCHEDULED_THREAT_DTYPE
