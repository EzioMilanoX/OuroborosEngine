# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IAudioClock via pygame.mixer.music.get_pos()."""
from __future__ import annotations

import pygame

from ouroboros.interfaces.audio_clock import IAudioClock


class PygameAudioClock(IAudioClock):
    """
    Implementacao de `IAudioClock` sobre `pygame.mixer.music.get_pos()`,
    com calibracao de latencia de saida.

    `pygame.mixer.music.get_pos()` retorna milissegundos desde a ultima
    chamada a `play()`, sempre reiniciando em 0 -- nao inclui um
    eventual `start_offset_seconds` passado a `play()`. Por isso
    `PygameAudioEngine.play_track` chama `_set_start_offset` nesta
    instancia para que `now_seconds()` reflita a posicao ABSOLUTA na
    faixa, nao apenas o tempo decorrido desde o inicio desta chamada de
    reproducao.

    `now_seconds()` so confia em `get_pos()` quando `is_playing()`
    (`get_busy()`) e verdadeiro. Isso NAO e defensivo por excesso de
    cautela: confirmado empiricamente que o driver "dummy" do SDL usado
    em testes headless deixa `get_pos()` com um valor positivo e
    crescente "sujo" mesmo depois de `stop()`/`pygame.quit()`/reinit do
    mixer, MESMO quando nada esta tocando (`get_busy()` volta
    corretamente a `False`, `get_pos()` nao). Sem esta guarda,
    `now_seconds()` de um clock que nunca tocou nada NESTA sessao mas
    roda no mesmo processo que ja tocou algo antes (comum em testes)
    reportaria um tempo de reproducao falso, positivo e crescente --
    quebrando o contrato de `IAudioClock` ("tempo REAL de reproducao,
    nunca um acumulador").
    """

    def __init__(self) -> None:
        self._output_latency_seconds = 0.0
        self._playback_rate = 1.0
        self._start_offset_seconds = 0.0

    def _set_start_offset(self, start_offset_seconds: float) -> None:
        """Chamado por `PygameAudioEngine.play_track` a cada novo `play()`."""
        self._start_offset_seconds = start_offset_seconds

    def now_seconds(self) -> float:
        if not self.is_playing():
            return 0.0
        pos_ms = pygame.mixer.music.get_pos()
        if pos_ms < 0:
            return 0.0
        return self._start_offset_seconds + (pos_ms / 1000.0)

    def is_playing(self) -> bool:
        return bool(pygame.mixer.music.get_busy())

    def get_playback_rate(self) -> float:
        return self._playback_rate

    def get_output_latency_seconds(self) -> float:
        return self._output_latency_seconds

    def calibrate_latency(self, offset_seconds: float) -> None:
        self._output_latency_seconds = offset_seconds
