# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Carrega um arquivo de audio bruto em memoria, normalizado para as etapas de extracao."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

import librosa


@dataclass(frozen=True)
class LoadedAudio:
    """Audio decodificado em memoria, pronto para as etapas de extracao.

    Atributos:
        samples: forma `(n_samples,)`, `float32`, mono (apos
            normalizacao por `AudioLoader`).
        sample_rate: taxa de amostragem em Hz, apos normalizacao.
        source_path: caminho do arquivo original (logging/erro).
    """

    samples: np.ndarray
    sample_rate: int
    source_path: Path


class AudioLoadError(Exception):
    """Levantado quando o arquivo de audio nao existe, nao pode ser
    decodificado, ou resulta em um sinal vazio/silencioso demais para
    analise.
    """


class AudioLoader:
    """Carrega um arquivo de audio bruto em memoria, normalizado para as
    etapas seguintes do pipeline.

    Isolada em sua propria classe para ser testavel de forma independente
    (ex.: testar com um WAV sintetico curto sem rodar extracao de BPM/
    onset). Roda 100% fora do loop de gameplay.
    """

    def __init__(self, target_sample_rate: int = 22050, mono: bool = True) -> None:
        """Define a taxa de amostragem alvo e se o audio deve ser reduzido
        para mono antes de seguir para as etapas de extracao.
        """
        self._target_sample_rate = target_sample_rate
        self._mono = mono

    def load(self, audio_path: Path) -> LoadedAudio:
        """Decodifica `audio_path` (via `librosa.load` internamente) e
        retorna um `LoadedAudio` normalizado.

        Levanta `AudioLoadError` se o arquivo nao existir, nao puder ser
        decodificado, ou resultar em audio vazio.
        """
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise AudioLoadError(f"audio file not found: {audio_path}")

        try:
            samples, sample_rate = librosa.load(
                str(audio_path), sr=self._target_sample_rate, mono=self._mono
            )
        except Exception as exc:  # librosa/soundfile/audioread podem levantar varios tipos
            raise AudioLoadError(f"failed to decode audio file {audio_path}: {exc}") from exc

        samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            raise AudioLoadError(f"audio file decoded to an empty signal: {audio_path}")
        if not np.any(samples):
            raise AudioLoadError(f"audio file decoded to a silent (all-zero) signal: {audio_path}")

        return LoadedAudio(samples=samples, sample_rate=int(sample_rate), source_path=audio_path)
