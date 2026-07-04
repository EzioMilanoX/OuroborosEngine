"""Testa BeatmapValidator.validate/build_beatmap_dict com casos validos e invalidos."""
from __future__ import annotations

import copy

import pytest

from ouroboros.rhythm.beatmap_format import BEATMAP_SCHEMA_VERSION
from ouroboros.rhythm.offline.beatmap_schema import (
    BeatmapValidationError,
    BeatmapValidator,
    ScheduledThreatDefinition,
)


def _valid_beatmap_dict():
    return {
        "version": BEATMAP_SCHEMA_VERSION,
        "track_id": "test_track",
        "bpm": 128.0,
        "threats": [
            {"timestamp_seconds": 0.5, "threat_type": "rhythm_threat_basic", "lane": 0, "strength": 0.8},
            {"timestamp_seconds": 1.0, "threat_type": "rhythm_threat_basic", "lane": 1, "strength": 0.5},
            {"timestamp_seconds": 1.0, "threat_type": "rhythm_threat_basic", "lane": 2, "strength": 0.2},
        ],
    }


def test_validate_accepts_well_formed_beatmap():
    validator = BeatmapValidator()
    validator.validate(_valid_beatmap_dict())  # nao deve levantar


def test_validate_accepts_empty_threats_list():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    beatmap["threats"] = []
    validator.validate(beatmap)


@pytest.mark.parametrize("missing_root_field", ["version", "track_id", "bpm", "threats"])
def test_validate_rejects_missing_root_field(missing_root_field):
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    del beatmap[missing_root_field]

    with pytest.raises(BeatmapValidationError, match=missing_root_field):
        validator.validate(beatmap)


@pytest.mark.parametrize(
    "missing_threat_field", ["timestamp_seconds", "threat_type", "lane", "strength"]
)
def test_validate_rejects_missing_threat_field(missing_threat_field):
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    del beatmap["threats"][0][missing_threat_field]

    with pytest.raises(BeatmapValidationError, match=missing_threat_field):
        validator.validate(beatmap)


def test_validate_rejects_unknown_schema_version():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    beatmap["version"] = BEATMAP_SCHEMA_VERSION + 999

    with pytest.raises(BeatmapValidationError):
        validator.validate(beatmap)


def test_validate_rejects_out_of_order_timestamps():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    beatmap["threats"] = [
        {"timestamp_seconds": 2.0, "threat_type": "rhythm_threat_basic", "lane": 0, "strength": 0.5},
        {"timestamp_seconds": 1.0, "threat_type": "rhythm_threat_basic", "lane": 1, "strength": 0.5},
    ]

    with pytest.raises(BeatmapValidationError):
        validator.validate(beatmap)


def test_validate_rejects_strength_out_of_range():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    beatmap["threats"][0]["strength"] = 1.5

    with pytest.raises(BeatmapValidationError):
        validator.validate(beatmap)


def test_validate_rejects_negative_lane():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    beatmap["threats"][0]["lane"] = -1

    with pytest.raises(BeatmapValidationError):
        validator.validate(beatmap)


def test_validate_rejects_non_dict_document():
    validator = BeatmapValidator()

    with pytest.raises(BeatmapValidationError):
        validator.validate(["not", "a", "dict"])


def test_validate_does_not_mutate_input():
    validator = BeatmapValidator()
    beatmap = _valid_beatmap_dict()
    snapshot = copy.deepcopy(beatmap)

    validator.validate(beatmap)

    assert beatmap == snapshot


def test_build_beatmap_dict_sorts_by_timestamp_and_sets_version():
    validator = BeatmapValidator()
    threats = (
        ScheduledThreatDefinition(timestamp_seconds=2.0, threat_type="rhythm_threat_basic", lane=1, strength=0.4),
        ScheduledThreatDefinition(timestamp_seconds=1.0, threat_type="rhythm_threat_basic", lane=0, strength=0.9),
    )

    beatmap = validator.build_beatmap_dict(track_id="my_track", bpm=140.0, threats=threats)

    assert beatmap["version"] == BEATMAP_SCHEMA_VERSION
    assert beatmap["track_id"] == "my_track"
    assert beatmap["bpm"] == 140.0
    timestamps = [t["timestamp_seconds"] for t in beatmap["threats"]]
    assert timestamps == sorted(timestamps)
    assert timestamps == [1.0, 2.0]

    # O resultado de build_beatmap_dict deve, por construcao, ser valido.
    validator.validate(beatmap)
