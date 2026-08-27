# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrato de reproducao de audio/efeitos sonoros (IAudioEngine)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ouroboros.interfaces.audio_clock import IAudioClock


class IAudioEngine(ABC):
    """
    Contrato de reproducao de audio/efeitos sonoros. Recebe apenas
    identificadores/caminhos e valores primitivos -- nunca objetos de
    jogo ou tipos de uma biblioteca de audio concreta.
    """

    @abstractmethod
    def load_track(self, track_id: str, file_path: str) -> None:
        """Carrega a faixa musical `file_path` sob o identificador `track_id`, fora do loop de gameplay."""
        ...

    @abstractmethod
    def play_track(self, track_id: str, start_offset_seconds: float = 0.0, loop: bool = False) -> None:
        """Inicia a reproducao de `track_id` e (re)inicializa o `IAudioClock` retornado por `get_clock()`."""
        ...

    @abstractmethod
    def stop_track(self, track_id: str) -> None:
        """Interrompe a reproducao de `track_id`, se estiver tocando."""
        ...

    @abstractmethod
    def load_sound(self, sound_id: str, file_path: str) -> None:
        """Pre-carrega e cacheia `file_path` como um efeito sonoro curto sob o
        nome `sound_id`, fora do loop de gameplay -- espelha `load_track`, mas
        para uma amostra ONE-SHOT (`play_one_shot`), nao uma faixa em stream.
        Da a uma amostra baseada em arquivo um nome amigavel, simetrico ao que
        `register_tone` ja permite para um som sintetizado."""
        ...

    @abstractmethod
    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        """Dispara um efeito sonoro curto identificado por `sound_id`, sem afetar `get_clock()`."""
        ...

    @abstractmethod
    def get_clock(self) -> IAudioClock:
        """Retorna o `IAudioClock` associado a faixa musical atualmente em reproducao."""
        ...

    # ------------------------------------------------------------------
    # SFX procedural (ROADMAP M4): metodo NAO-abstrato com default no-op —
    # permite jogos sem assets de audio sintetizarem efeitos curtos.
    # Chamado na composicao/cena (fora do loop de gameplay).
    # ------------------------------------------------------------------

    def register_tone(self, sound_id: str, kind: str = "square",
                      freq: float = 440.0, duration: float = 0.12) -> None:
        """Sintetiza e registra um efeito curto sob `sound_id`, tocavel
        depois via `play_one_shot`. `kind`: square | noise | sweep | zap.
        Default: no-op (backends sem suporte ignoram)."""
