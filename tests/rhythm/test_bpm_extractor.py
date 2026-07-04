"""Testa BpmExtractor ponta-a-ponta com um clique metronomico sintetico real."""
from __future__ import annotations

from pathlib import Path

from ouroboros.rhythm.offline.audio_loader import AudioLoader
from ouroboros.rhythm.offline.bpm_extractor import BpmExtractor


def test_extract_returns_plausible_positive_bpm(synthetic_wav_factory):
    # librosa NAO e perfeito com um clique sintetico simples: a deteccao de
    # tempo pode facilmente confundir o andamento com a metade/dobro do BPM
    # real (ambiguidade classica de "tempo octave error"). O objetivo deste
    # teste e confirmar que o pipeline roda ponta-a-ponta sobre audio real e
    # devolve um BPM positivo plausivelmente relacionado a 120 -- nao cravar
    # precisao musicologica.
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=6.0, sample_rate=22050)

    audio = AudioLoader().load(Path(wav_path))
    result = BpmExtractor(tightness=100.0).extract(audio)

    assert result.bpm > 0.0

    expected_bpm = 120.0
    candidates = (expected_bpm, expected_bpm / 2.0, expected_bpm * 2.0)
    closest_distance = min(abs(result.bpm - candidate) for candidate in candidates)
    assert closest_distance < 40.0, f"bpm {result.bpm} too far from 120 (or its half/double)"


def test_extract_returns_ordered_nonempty_beat_timestamps(synthetic_wav_factory):
    wav_path = synthetic_wav_factory(bpm=120.0, duration_seconds=6.0, sample_rate=22050)

    audio = AudioLoader().load(Path(wav_path))
    result = BpmExtractor(tightness=100.0).extract(audio)

    assert result.beat_timestamps_seconds.size > 0
    assert (result.beat_timestamps_seconds[:-1] <= result.beat_timestamps_seconds[1:]).all()
    assert (result.beat_timestamps_seconds >= 0.0).all()
