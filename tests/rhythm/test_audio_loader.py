# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa AudioLoader com um WAV sintetico real (sem mock de librosa)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ouroboros.rhythm.offline.audio_loader import AudioLoader, AudioLoadError


def test_load_synthetic_wav_returns_mono_float32_samples(synthetic_wav_factory):
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=2.0, sample_rate=22050)

    loader = AudioLoader(target_sample_rate=22050, mono=True)
    loaded = loader.load(Path(wav_path))

    assert loaded.samples.dtype == np.float32
    assert loaded.samples.ndim == 1
    assert loaded.samples.size > 0
    assert np.any(loaded.samples)
    assert loaded.sample_rate == 22050
    assert loaded.source_path == Path(wav_path)


def test_load_resamples_to_target_sample_rate(synthetic_wav_factory):
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=1.0, sample_rate=44100)

    loader = AudioLoader(target_sample_rate=16000, mono=True)
    loaded = loader.load(Path(wav_path))

    assert loaded.sample_rate == 16000


def test_load_nonexistent_file_raises_audio_load_error(tmp_path):
    loader = AudioLoader()
    missing_path = tmp_path / "does_not_exist.wav"

    with pytest.raises(AudioLoadError):
        loader.load(missing_path)


def test_load_empty_wav_raises_audio_load_error(tmp_path):
    import wave

    empty_path = tmp_path / "empty.wav"
    with wave.open(str(empty_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"")

    loader = AudioLoader()
    with pytest.raises(AudioLoadError):
        loader.load(empty_path)


def test_load_silent_wav_raises_audio_load_error(tmp_path):
    import wave

    silent_path = tmp_path / "silent.wav"
    sample_rate = 22050
    n_samples = sample_rate  # 1 second of silence
    silence = np.zeros(n_samples, dtype=np.int16)
    with wave.open(str(silent_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence.tobytes())

    loader = AudioLoader()
    with pytest.raises(AudioLoadError):
        loader.load(silent_path)
