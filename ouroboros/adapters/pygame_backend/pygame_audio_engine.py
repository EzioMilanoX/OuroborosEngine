"""Implementacao concreta de IAudioEngine sobre pygame.mixer."""
from __future__ import annotations

import pygame

from ouroboros.adapters.pygame_backend.pygame_audio_clock import PygameAudioClock
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine


class PygameAudioEngine(IAudioEngine):
    """
    Implementacao de `IAudioEngine` sobre `pygame.mixer`/`pygame.mixer.music`.

    `play_one_shot` trata `sound_id` como o CAMINHO do arquivo de efeito
    sonoro (a ABC `IAudioEngine` nao define um `load_sound` separado de
    `load_track`); sons carregados sao cacheados por `sound_id` para
    nao recarregar o arquivo a cada disparo.
    """

    def __init__(self) -> None:
        """Cria o `PygameAudioClock` interno retornado por `get_clock()`."""
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self._clock = PygameAudioClock()
        self._loaded_tracks = {}
        self._current_track_id = None
        self._sounds = {}

    def load_track(self, track_id: str, file_path: str) -> None:
        self._loaded_tracks[track_id] = file_path

    def play_track(self, track_id: str, start_offset_seconds: float = 0.0, loop: bool = False) -> None:
        file_path = self._loaded_tracks[track_id]
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play(loops=-1 if loop else 0, start=start_offset_seconds)
        self._clock._set_start_offset(start_offset_seconds)
        self._current_track_id = track_id

    def stop_track(self, track_id: str) -> None:
        if self._current_track_id == track_id:
            pygame.mixer.music.stop()
            self._current_track_id = None

    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        sound = self._sounds.get(sound_id)
        if sound is None:
            sound = pygame.mixer.Sound(sound_id)
            self._sounds[sound_id] = sound
        sound.set_volume(volume)
        sound.play()

    def get_clock(self) -> IAudioClock:
        return self._clock
