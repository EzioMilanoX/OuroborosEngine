# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pipeline offline completo ponta-a-ponta: audio sintetico -> beatmap.json valido."""
from __future__ import annotations

import json
from pathlib import Path

from ouroboros.rhythm.offline.audio_ai_processor import AudioAIProcessor
from ouroboros.rhythm.offline.audio_loader import AudioLoader
from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidator
from ouroboros.rhythm.offline.beatmap_writer import BeatmapWriter
from ouroboros.rhythm.offline.bpm_extractor import BpmExtractor
from ouroboros.rhythm.offline.onset_extractor import OnsetExtractor


def _build_processor(lane_count: int = 4) -> AudioAIProcessor:
    return AudioAIProcessor(
        audio_loader=AudioLoader(),
        bpm_extractor=BpmExtractor(),
        onset_extractor=OnsetExtractor(),
        beatmap_validator=BeatmapValidator(),
        beatmap_writer=BeatmapWriter(BeatmapValidator()),
        lane_count=lane_count,
    )


def test_process_generates_valid_beatmap_with_threats(tmp_path, synthetic_wav_factory):
    wav_path = Path(synthetic_wav_factory(bpm=120.0, duration_seconds=6.0, sample_rate=22050))
    output_path = tmp_path / "beatmap.json"

    processor = _build_processor(lane_count=4)
    result = processor.process(audio_path=wav_path, beatmap_output_path=output_path, track_id="synthetic_track")

    assert output_path.is_file()
    assert result.beatmap_path == output_path
    assert result.threat_count > 0

    with open(output_path, "r", encoding="utf-8") as f:
        beatmap_dict = json.load(f)

    # O proprio validator deve aceitar o resultado escrito em disco.
    BeatmapValidator().validate(beatmap_dict)

    assert beatmap_dict["track_id"] == "synthetic_track"
    assert len(beatmap_dict["threats"]) == result.threat_count
    assert beatmap_dict["bpm"] == result.bpm_result.bpm


def test_process_distributes_lanes_deterministically(tmp_path, synthetic_wav_factory):
    wav_path = Path(synthetic_wav_factory(bpm=120.0, duration_seconds=6.0, sample_rate=22050))
    output_path = tmp_path / "beatmap.json"

    processor = _build_processor(lane_count=3)
    result = processor.process(audio_path=wav_path, beatmap_output_path=output_path, track_id="lane_track")

    with open(output_path, "r", encoding="utf-8") as f:
        beatmap_dict = json.load(f)

    for threat in beatmap_dict["threats"]:
        assert 0 <= threat["lane"] < 3
        assert threat["threat_type"] == "rhythm_threat_basic"


def test_process_is_deterministic_across_runs(tmp_path, synthetic_wav_factory):
    wav_path = Path(synthetic_wav_factory(bpm=120.0, duration_seconds=4.0, sample_rate=22050))

    output_1 = tmp_path / "beatmap_1.json"
    output_2 = tmp_path / "beatmap_2.json"

    _build_processor().process(audio_path=wav_path, beatmap_output_path=output_1, track_id="t")
    _build_processor().process(audio_path=wav_path, beatmap_output_path=output_2, track_id="t")

    with open(output_1, "r", encoding="utf-8") as f:
        content_1 = json.load(f)
    with open(output_2, "r", encoding="utf-8") as f:
        content_2 = json.load(f)

    assert content_1 == content_2
