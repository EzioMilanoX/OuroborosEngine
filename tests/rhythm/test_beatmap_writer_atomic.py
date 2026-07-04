"""Testa a escrita atomica de BeatmapWriter (tmp + fsync + os.replace)."""
from __future__ import annotations

import json

import pytest

from ouroboros.rhythm.beatmap_format import BEATMAP_SCHEMA_VERSION
from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidationError, BeatmapValidator
from ouroboros.rhythm.offline.beatmap_writer import BeatmapWriter


def _valid_beatmap_dict():
    return {
        "version": BEATMAP_SCHEMA_VERSION,
        "track_id": "atomic_test_track",
        "bpm": 100.0,
        "threats": [
            {"timestamp_seconds": 0.25, "threat_type": "rhythm_threat_basic", "lane": 0, "strength": 1.0},
        ],
    }


def test_write_then_read_back_matches_content(tmp_path):
    destination = tmp_path / "beatmap.json"
    writer = BeatmapWriter(BeatmapValidator())
    beatmap = _valid_beatmap_dict()

    writer.write(beatmap, destination)

    assert destination.is_file()
    with open(destination, "r", encoding="utf-8") as f:
        written = json.load(f)
    assert written == beatmap


def test_write_leaves_no_orphan_temp_file_on_success(tmp_path):
    destination = tmp_path / "beatmap.json"
    writer = BeatmapWriter(BeatmapValidator())

    writer.write(_valid_beatmap_dict(), destination)

    remaining_files = sorted(p.name for p in tmp_path.iterdir())
    assert remaining_files == [destination.name]


def test_write_invalid_beatmap_raises_and_writes_nothing(tmp_path):
    destination = tmp_path / "beatmap.json"
    writer = BeatmapWriter(BeatmapValidator())
    invalid_beatmap = _valid_beatmap_dict()
    del invalid_beatmap["bpm"]

    with pytest.raises(BeatmapValidationError):
        writer.write(invalid_beatmap, destination)

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_does_not_overwrite_existing_valid_file_when_new_content_is_invalid(tmp_path):
    destination = tmp_path / "beatmap.json"
    writer = BeatmapWriter(BeatmapValidator())
    original = _valid_beatmap_dict()
    writer.write(original, destination)

    invalid_beatmap = _valid_beatmap_dict()
    invalid_beatmap["threats"][0]["strength"] = 5.0  # fora de [0, 1]

    with pytest.raises(BeatmapValidationError):
        writer.write(invalid_beatmap, destination)

    with open(destination, "r", encoding="utf-8") as f:
        surviving_content = json.load(f)
    assert surviving_content == original


def test_write_overwrites_existing_file_atomically(tmp_path):
    destination = tmp_path / "beatmap.json"
    writer = BeatmapWriter(BeatmapValidator())

    first = _valid_beatmap_dict()
    writer.write(first, destination)

    second = _valid_beatmap_dict()
    second["bpm"] = 200.0
    writer.write(second, destination)

    with open(destination, "r", encoding="utf-8") as f:
        content = json.load(f)
    assert content["bpm"] == 200.0
    # nenhum temporario orfao apos a segunda escrita
    assert sorted(p.name for p in tmp_path.iterdir()) == [destination.name]
