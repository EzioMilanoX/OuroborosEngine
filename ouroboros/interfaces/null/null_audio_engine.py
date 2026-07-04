"""Implementacao nula de IAudioEngine; nao reproduz som real."""
from __future__ import annotations

from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.null.null_audio_clock import NullAudioClock


class NullAudioEngine(IAudioEngine):
    """
    Implementacao nula de `IAudioEngine`; nao reproduz som real. Expoe
    um `NullAudioClock` interno via `get_clock()`, permitindo
    exercitar `RhythmSpawnerSystem` em testes headless (Pilar 5).
    """

    def __init__(self) -> None:
        """Cria o `NullAudioClock` interno retornado por `get_clock()`. Construcao ocorre fora do loop de gameplay (setup de teste)."""
        self._clock = NullAudioClock()
        self._loaded_tracks = {}
        self._playing_track_id = None
        self._one_shots_played = []

    def load_track(self, track_id: str, file_path: str) -> None:
        self._loaded_tracks[track_id] = file_path

    def play_track(self, track_id: str, start_offset_seconds: float = 0.0, loop: bool = False) -> None:
        self._playing_track_id = track_id
        self._clock.set_now_seconds(start_offset_seconds)
        self._clock.set_playing(True)

    def stop_track(self, track_id: str) -> None:
        if self._playing_track_id == track_id:
            self._playing_track_id = None
            self._clock.set_playing(False)

    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        self._one_shots_played.append((sound_id, volume))

    def get_clock(self) -> IAudioClock:
        return self._clock
