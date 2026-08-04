# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa OnsetExtractor ponta-a-ponta com o mesmo audio sintetico real."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ouroboros.rhythm.offline.audio_loader import AudioLoader
from ouroboros.rhythm.offline.onset_extractor import OnsetExtractor


def test_extract_detects_some_onsets_with_normalized_strengths(synthetic_wav_factory):
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=6.0, sample_rate=22050)

    audio = AudioLoader().load(Path(wav_path))
    result = OnsetExtractor(backtrack=True, units="time").extract(audio)

    assert result.onset_timestamps_seconds.size > 0
    assert result.onset_strengths.size == result.onset_timestamps_seconds.size

    assert (result.onset_strengths >= 0.0).all()
    assert (result.onset_strengths <= 1.0).all()

    # Timestamps sao ordenados (librosa.onset.onset_detect ja garante isso,
    # mas a invariante e parte do contrato consumido pelo restante do pipeline).
    assert (result.onset_timestamps_seconds[:-1] <= result.onset_timestamps_seconds[1:]).all()


def test_extract_strengths_are_float32(synthetic_wav_factory):
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=4.0, sample_rate=22050)

    audio = AudioLoader().load(Path(wav_path))
    result = OnsetExtractor().extract(audio)

    assert result.onset_strengths.dtype == np.float32
