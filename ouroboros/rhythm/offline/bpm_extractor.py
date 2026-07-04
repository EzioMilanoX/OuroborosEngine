"""Wrapper fino sobre librosa.beat.beat_track."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import librosa

from ouroboros.rhythm.offline.audio_loader import LoadedAudio


@dataclass(frozen=True)
class BpmExtractionResult:
    """Resultado da extracao de tempo (BPM) de um audio.

    Atributos:
        bpm: andamento estimado, em batidas por minuto.
        beat_timestamps_seconds: array ordenado (`float64`) com o
            instante, em segundos, de cada batida detectada.
    """

    bpm: float
    beat_timestamps_seconds: np.ndarray


class BpmExtractionError(Exception):
    """Levantado quando `librosa.beat.beat_track` falha ou retorna um
    resultado degenerado (BPM nao-positivo, nenhuma batida detectada em
    um audio nao-silencioso).
    """


class BpmExtractor:
    """Wrapper fino sobre `librosa.beat.beat_track`.

    Isolada para ser testavel de forma independente (ex.: com um clique
    metronomico sintetico de BPM conhecido). Roda 100% fora do loop de
    gameplay; nunca e importada pelo pacote `runtime`.
    """

    def __init__(self, tightness: float = 100.0) -> None:
        """Configura o parametro `tightness` repassado a
        `librosa.beat.beat_track` (rigidez do rastreamento de batida).
        """
        self._tightness = tightness

    def extract(self, audio: LoadedAudio) -> BpmExtractionResult:
        """Roda `librosa.beat.beat_track` sobre `audio.samples` e
        converte frames para segundos usando `audio.sample_rate`.

        Levanta `BpmExtractionError` se o resultado for degenerado.
        """
        try:
            tempo, beat_times = librosa.beat.beat_track(
                y=audio.samples,
                sr=audio.sample_rate,
                tightness=self._tightness,
                units="time",
            )
        except Exception as exc:
            raise BpmExtractionError(f"librosa.beat.beat_track failed: {exc}") from exc

        # Em versoes recentes do librosa, `tempo` pode vir como um array
        # numpy de 0 ou 1 elementos (em vez de um escalar Python puro) --
        # normalizamos sempre para um `float` primitivo.
        tempo_array = np.atleast_1d(np.asarray(tempo, dtype=np.float64))
        tempo_value = float(tempo_array[0]) if tempo_array.size > 0 else 0.0

        beat_timestamps_seconds = np.asarray(beat_times, dtype=np.float64)

        if tempo_value <= 0.0 or beat_timestamps_seconds.size == 0:
            raise BpmExtractionError(
                f"degenerate beat tracking result: bpm={tempo_value!r}, "
                f"beat_count={beat_timestamps_seconds.size}"
            )

        return BpmExtractionResult(bpm=tempo_value, beat_timestamps_seconds=beat_timestamps_seconds)
