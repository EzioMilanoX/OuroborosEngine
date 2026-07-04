"""Wrapper fino sobre librosa.onset.onset_detect."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import librosa

from ouroboros.rhythm.offline.audio_loader import LoadedAudio


@dataclass(frozen=True)
class OnsetExtractionResult:
    """Resultado da extracao de onsets (eventos sonoros distintos).

    Atributos:
        onset_timestamps_seconds: array ordenado (`float64`) com o
            instante, em segundos, de cada onset detectado.
        onset_strengths: array paralelo (`float32`, normalizado em
            `[0.0, 1.0]`) com a forca relativa de cada onset.
    """

    onset_timestamps_seconds: np.ndarray
    onset_strengths: np.ndarray


class OnsetExtractionError(Exception):
    """Levantado quando `librosa.onset.onset_detect`/`onset_strength`
    falha ou nao encontra nenhum onset em um audio nao-silencioso.
    """


class OnsetExtractor:
    """Wrapper fino sobre `librosa.onset.onset_detect`.

    Isolada para ser testavel de forma independente (ex.: com impulsos
    sinteticos espacados de forca conhecida). Roda 100% fora do loop de
    gameplay; nunca e importada pelo pacote `runtime`.
    """

    def __init__(self, backtrack: bool = True, units: str = "time") -> None:
        """Configura os parametros repassados a
        `librosa.onset.onset_detect`/`librosa.onset.onset_strength`.
        """
        self._backtrack = backtrack
        self._units = units

    def extract(self, audio: LoadedAudio) -> OnsetExtractionResult:
        """Roda a deteccao de onset sobre `audio.samples` e retorna
        timestamps ordenados com forcas relativas normalizadas.

        Levanta `OnsetExtractionError` em caso de falha da chamada
        librosa subjacente.
        """
        try:
            onset_events = librosa.onset.onset_detect(
                y=audio.samples,
                sr=audio.sample_rate,
                backtrack=self._backtrack,
                units=self._units,
            )
            strength_envelope = librosa.onset.onset_strength(y=audio.samples, sr=audio.sample_rate)
        except Exception as exc:
            raise OnsetExtractionError(f"librosa onset detection failed: {exc}") from exc

        onset_events = np.asarray(onset_events)
        if onset_events.size == 0:
            raise OnsetExtractionError("no onsets detected in non-silent audio")

        # `self._units` controla o que `onset_detect` retorna. Normalizamos
        # sempre para (timestamps em segundos, indices de frame), pois
        # precisamos dos indices de frame para indexar `strength_envelope`
        # (o envelope de forca completo, um valor por frame de analise) e
        # dos timestamps em segundos para `OnsetExtractionResult`.
        if self._units == "time":
            onset_timestamps_seconds = onset_events.astype(np.float64)
            frame_indices = librosa.time_to_frames(onset_timestamps_seconds, sr=audio.sample_rate)
        elif self._units == "samples":
            frame_indices = librosa.samples_to_frames(onset_events)
            onset_timestamps_seconds = librosa.samples_to_time(onset_events, sr=audio.sample_rate).astype(np.float64)
        else:  # "frames" (default do proprio librosa)
            frame_indices = onset_events.astype(np.int64)
            onset_timestamps_seconds = librosa.frames_to_time(frame_indices, sr=audio.sample_rate).astype(np.float64)

        # `time_to_frames`/backtracking podem produzir indices fora do
        # envelope (extremos do sinal); recortamos para o intervalo valido.
        frame_indices = np.clip(frame_indices, 0, strength_envelope.shape[0] - 1)

        # Forca de CADA onset detectado (nao o envelope inteiro): indexa o
        # envelope de forca nos frames correspondentes aos onsets.
        raw_strengths = strength_envelope[frame_indices].astype(np.float32)

        max_strength = float(raw_strengths.max()) if raw_strengths.size > 0 else 0.0
        if max_strength > 0.0:
            onset_strengths = (raw_strengths / max_strength).astype(np.float32)
        else:
            # Unico onset ou forca maxima zero: nao ha o que normalizar de
            # forma nao-degenerada; mantemos tudo em 0.0 (dentro de [0, 1]).
            onset_strengths = np.zeros_like(raw_strengths, dtype=np.float32)

        return OnsetExtractionResult(
            onset_timestamps_seconds=onset_timestamps_seconds,
            onset_strengths=onset_strengths,
        )
