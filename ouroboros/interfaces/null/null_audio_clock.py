# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao nula de IAudioClock, com tempo avancado manualmente por testes."""
from __future__ import annotations

from ouroboros.interfaces.audio_clock import IAudioClock


class NullAudioClock(IAudioClock):
    """
    Implementacao nula de `IAudioClock`, com tempo avancado
    manualmente por testes via `advance(seconds)` (fora do contrato da
    ABC) -- permite testar `RhythmSpawnerSystem` de forma
    deterministica e headless, sem dispositivo de audio real.
    """

    def __init__(self) -> None:
        """Inicializa o relogio nulo zerado, parado e sem latencia calibrada."""
        self._now_seconds = 0.0
        self._is_playing = False
        self._playback_rate = 1.0
        self._output_latency_seconds = 0.0

    def advance(self, seconds: float) -> None:
        """Avanca manualmente `now_seconds()` em `seconds`. Metodo de teste, fora do contrato de `IAudioClock`."""
        self._now_seconds += seconds

    def set_playing(self, is_playing: bool) -> None:
        """Define manualmente o estado de `is_playing()`. Metodo de teste, fora do contrato de `IAudioClock`."""
        self._is_playing = is_playing

    def set_now_seconds(self, now_seconds: float) -> None:
        """Define diretamente `now_seconds()`. Metodo de teste, fora do contrato de `IAudioClock`."""
        self._now_seconds = now_seconds

    def now_seconds(self) -> float:
        return self._now_seconds

    def is_playing(self) -> bool:
        return self._is_playing

    def get_playback_rate(self) -> float:
        return self._playback_rate

    def get_output_latency_seconds(self) -> float:
        return self._output_latency_seconds

    def calibrate_latency(self, offset_seconds: float) -> None:
        self._output_latency_seconds = offset_seconds
