# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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
        self._loaded_sounds = {}
        self._registered_tones = {}

    def load_track(self, track_id: str, file_path: str) -> None:
        self._loaded_tracks[track_id] = file_path

    def load_sound(self, sound_id: str, file_path: str) -> None:
        self._loaded_sounds[sound_id] = file_path

    def play_track(self, track_id: str, start_offset_seconds: float = 0.0, loop: bool = False) -> None:
        self._playing_track_id = track_id
        self._clock.set_now_seconds(start_offset_seconds)
        self._clock.set_playing(True)

    def stop_track(self, track_id: str) -> None:
        if self._playing_track_id == track_id:
            self._playing_track_id = None
            self._clock.set_playing(False)

    def pause_track(self, track_id: str) -> None:
        """Nao zera `_playing_track_id` (diferente de `stop_track`) -- `resume_track`
        precisa saber qual faixa retomar. `NullAudioClock.now_seconds()` nunca
        auto-avanca sozinho (so via `advance()`/`set_now_seconds()` explicitos de
        teste), entao nao precisa de nenhum estado de "congelado"."""
        if self._playing_track_id == track_id:
            self._clock.set_playing(False)

    def resume_track(self, track_id: str) -> None:
        if self._playing_track_id == track_id:
            self._clock.set_playing(True)

    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        self._one_shots_played.append((sound_id, volume))

    def get_clock(self) -> IAudioClock:
        return self._clock

    def register_tone(self, sound_id: str, kind: str = "square",
                      freq: float = 440.0, duration: float = 0.12) -> None:
        """Registra a chamada (para inspecao em teste), sem sintetizar nada de verdade."""
        self._registered_tones[sound_id] = (kind, freq, duration)
