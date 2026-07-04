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
    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        """Dispara um efeito sonoro curto identificado por `sound_id`, sem afetar `get_clock()`."""
        ...

    @abstractmethod
    def get_clock(self) -> IAudioClock:
        """Retorna o `IAudioClock` associado a faixa musical atualmente em reproducao."""
        ...
