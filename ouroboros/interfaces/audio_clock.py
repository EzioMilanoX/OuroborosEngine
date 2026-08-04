# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Fonte de verdade de tempo de reproducao de audio, consultada pelo jogo de ritmo."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IAudioClock(ABC):
    """
    Fonte de verdade de tempo de reproducao de audio -- separada de
    `IAudioEngine` por principio de menor privilegio: o
    `RhythmSpawnerSystem` (Pilar 4) so deve depender deste contrato
    minimo, testavel isoladamente com uma implementacao Null de avanco
    manual, sem precisar de um motor de audio completo.

    Invariante central: `now_seconds()` reflete o tempo REAL de
    reproducao do backend de audio (posicao do stream/dispositivo
    nativo) -- NUNCA um acumulador de delta-time somado pelo motor.
    Essa distincao e o que evita "drift" acumulado entre audio e
    gameplay no jogo musical.
    """

    @abstractmethod
    def now_seconds(self) -> float:
        """Tempo atual de reproducao da faixa ativa, em segundos, monotonico enquanto `is_playing()`."""
        ...

    @abstractmethod
    def is_playing(self) -> bool:
        """True se ha uma faixa de audio atualmente em reproducao (isto e, se o clock esta avancando)."""
        ...

    @abstractmethod
    def get_playback_rate(self) -> float:
        """Multiplicador de velocidade de reproducao atual (1.0 = velocidade normal; usado por modos de pratica)."""
        ...

    @abstractmethod
    def get_output_latency_seconds(self) -> float:
        """
        Latencia estimada de saida de audio do backend concreto (atraso
        do buffer do driver/dispositivo ate o som efetivamente chegar
        ao jogador), calibrada via `calibrate_latency`.
        `RhythmSpawnerSystem` deve compensar `now_seconds()` com este
        valor ao decidir se um evento do beatmap ja deveria ter sido
        disparado -- sem isso, o jogo tende a parecer "atrasado" mesmo
        com um clock logicamente correto.
        """
        ...

    @abstractmethod
    def calibrate_latency(self, offset_seconds: float) -> None:
        """Ajusta a latencia de saida assumida (ex.: via uma tela de calibracao jogada pelo usuario)."""
        ...
