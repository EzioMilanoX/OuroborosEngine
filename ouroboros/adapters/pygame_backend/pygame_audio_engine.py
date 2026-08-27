# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Implementacao concreta de IAudioEngine sobre pygame.mixer."""
from __future__ import annotations

import numpy as np
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

    def load_sound(self, sound_id: str, file_path: str) -> None:
        self._sounds[sound_id] = pygame.mixer.Sound(file_path)

    def play_one_shot(self, sound_id: str, volume: float = 1.0) -> None:
        sound = self._sounds.get(sound_id)
        if sound is None:
            sound = pygame.mixer.Sound(sound_id)
            self._sounds[sound_id] = sound
        sound.set_volume(volume)
        sound.play()

    def get_clock(self) -> IAudioClock:
        return self._clock

    def register_tone(self, sound_id: str, kind: str = "square",
                      freq: float = 440.0, duration: float = 0.12) -> None:
        """SFX procedural (ROADMAP M4): sintetiza a forma de onda com
        NumPy e registra como Sound — nenhum arquivo de audio necessario.
        Chamar na composicao (aloca), nunca no loop de gameplay."""
        init = pygame.mixer.get_init()
        if init is None:
            pygame.mixer.init()
            init = pygame.mixer.get_init()
        sample_rate, _fmt, channels = init
        n = max(1, int(sample_rate * duration))
        t = np.arange(n, dtype=np.float32) / sample_rate
        env = np.exp(-t * (5.0 / max(duration, 1e-3)))     # decaimento
        if kind == "noise":
            base = np.random.default_rng(hash(sound_id) & 0xFFFF).uniform(
                -1.0, 1.0, n).astype(np.float32)
        elif kind == "sweep":                              # desce (explosao)
            f = freq * (1.0 - 0.7 * t / max(duration, 1e-3))
            base = np.sign(np.sin(2 * np.pi * np.cumsum(f) / sample_rate))
        elif kind == "zap":                                # sobe (EMP)
            f = freq * (1.0 + 2.5 * t / max(duration, 1e-3))
            base = np.sin(2 * np.pi * np.cumsum(f) / sample_rate)
        else:                                              # square
            base = np.sign(np.sin(2 * np.pi * freq * t))
        wave = (base * env * 0.5 * 32767).astype(np.int16)
        if channels > 1:
            wave = np.repeat(wave[:, None], channels, axis=1)
        self._sounds[sound_id] = pygame.sndarray.make_sound(
            np.ascontiguousarray(wave))
