# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testa os adapters concretos de Pygame (Pilar 2) contra os drivers
SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy forcados em conftest.py -- sem
janela nem dispositivo de audio real.
"""
import json
import time

import numpy as np
import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_audio_engine import PygameAudioEngine
from ouroboros.adapters.pygame_backend.pygame_input_provider import PygameInputProvider
from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer, SHAPE_CIRCLE, SHAPE_RING


@pytest.fixture
def pygame_renderer():
    renderer = PygameRenderer()
    renderer.initialize(width=320, height=240, title="test")
    yield renderer
    renderer.shutdown()


def test_pygame_renderer_is_a_real_irenderer_and_initializes_headless(pygame_renderer):
    assert isinstance(pygame_renderer, IRenderer)
    assert pygame_renderer.get_viewport_size() == (320, 240)


def test_pygame_renderer_draw_batch_runs_without_a_real_display(pygame_renderer):
    pygame_renderer.begin_frame()
    positions_xy = np.array([[10.0, 10.0], [50.0, 50.0]], dtype=np.float32)
    rotations_rad = np.zeros(2, dtype=np.float32)
    scales_xy = np.ones((2, 2), dtype=np.float32)
    texture_ids = np.array([1, 2], dtype=np.uint32)
    tint_rgba = np.array([[255, 0, 0, 255], [0, 255, 0, 255]], dtype=np.uint8)
    layer_z = np.array([0, 1], dtype=np.int16)

    pygame_renderer.draw_batch(positions_xy, rotations_rad, scales_xy, texture_ids, tint_rgba, layer_z, 2)
    pygame_renderer.end_frame()  # must not raise even without a real window


def test_pygame_renderer_draw_batch_with_zero_count_is_noop(pygame_renderer):
    empty_xy = np.zeros((0, 2), dtype=np.float32)
    empty_1d = np.zeros(0, dtype=np.float32)
    empty_int = np.zeros(0, dtype=np.int64)
    empty_rgba = np.zeros((0, 4), dtype=np.uint8)
    pygame_renderer.begin_frame()
    pygame_renderer.draw_batch(empty_xy, empty_1d, empty_xy, empty_int, empty_rgba, empty_int, 0)
    pygame_renderer.end_frame()


def test_pygame_renderer_draw_batch_renders_ring_outline_not_filled(pygame_renderer):
    """SHAPE_RING (ROADMAP M1.1) desenha um contorno, nao um circulo preenchido: o
    centro deve permanecer com a cor de fundo, mas a borda (a `radius` pixels do
    centro) deve ter a cor do tint."""
    pygame_renderer.begin_frame()
    positions_xy = np.array([[50.0, 50.0]], dtype=np.float32)
    rotations_rad = np.zeros(1, dtype=np.float32)
    scales_xy = np.array([[6.0, 6.0]], dtype=np.float32)  # width=height=48 -> radius=24
    texture_ids = np.array([SHAPE_RING], dtype=np.uint32)
    tint_rgba = np.array([[255, 0, 0, 255]], dtype=np.uint8)
    layer_z = np.zeros(1, dtype=np.int16)

    pygame_renderer.draw_batch(positions_xy, rotations_rad, scales_xy, texture_ids, tint_rgba, layer_z, 1)
    pygame_renderer.end_frame()

    surface = pygame.display.get_surface()
    center = tuple(surface.get_at((50, 50)))[:3]
    # A borda exata do circulo (raio=24) pode cair 1px pra dentro/fora dependendo do
    # arredondamento do SDL -- sonda uma pequena faixa em vez de um unico pixel exato.
    ring_pixels = [tuple(surface.get_at((50 + offset, 50)))[:3] for offset in range(20, 26)]
    assert center != (255, 0, 0)
    assert (255, 0, 0) in ring_pixels


def test_pygame_renderer_draw_effects_runs_without_a_real_display(pygame_renderer):
    pygame_renderer.begin_frame()
    kinds = np.array([SHAPE_CIRCLE], dtype=np.uint32)
    positions_xy = np.array([[20.0, 20.0]], dtype=np.float32)
    sizes_wh = np.array([[10.0, 10.0]], dtype=np.float32)
    tint_rgba = np.array([[0, 255, 0, 255]], dtype=np.uint8)

    pygame_renderer.draw_effects(kinds, positions_xy, sizes_wh, tint_rgba, 1)
    pygame_renderer.end_frame()  # must not raise even without a real window


def test_pygame_renderer_draw_effects_with_zero_count_is_noop(pygame_renderer):
    empty_kinds = np.zeros(0, dtype=np.uint32)
    empty_xy = np.zeros((0, 2), dtype=np.float32)
    empty_rgba = np.zeros((0, 4), dtype=np.uint8)
    pygame_renderer.begin_frame()
    pygame_renderer.draw_effects(empty_kinds, empty_xy, empty_xy, empty_rgba, 0)
    pygame_renderer.end_frame()


@pytest.fixture
def bindings_path(tmp_path):
    path = tmp_path / "bindings.json"
    path.write_text(
        json.dumps({"fire": "KEY_SPACE", "move_right": "KEY_D", "aim": "MOUSE_LEFT"}),
        encoding="utf-8",
    )
    return str(path)


def test_pygame_input_provider_resolves_and_polls_bindings(bindings_path):
    pygame.display.init()  # required for pygame.key.get_pressed() under some SDL video drivers
    provider = PygameInputProvider()
    assert isinstance(provider, IInputProvider)
    provider.load_bindings(bindings_path)

    provider.poll()  # must not raise even though nothing is pressed

    assert provider.is_action_held("fire") is False
    assert provider.wants_quit() is False


def test_pygame_input_provider_set_rumble_is_a_silent_noop_without_a_joystick():
    provider = PygameInputProvider()
    provider.set_rumble(1.0, 1.0, 0.1)  # nao ha controle conectado -- nunca levanta


def test_pygame_input_provider_rejects_unknown_binding_code(tmp_path):
    path = tmp_path / "bad_bindings.json"
    path.write_text(json.dumps({"fire": "GAMEPAD_A"}), encoding="utf-8")
    provider = PygameInputProvider()
    with pytest.raises(ValueError):
        provider.load_bindings(str(path))


@pytest.fixture
def pygame_audio_engine():
    engine = PygameAudioEngine()
    yield engine
    pygame.mixer.quit()


def test_pygame_audio_engine_is_a_real_iaudioengine(pygame_audio_engine):
    assert isinstance(pygame_audio_engine, IAudioEngine)
    clock = pygame_audio_engine.get_clock()
    assert isinstance(clock, IAudioClock)
    assert clock.now_seconds() == 0.0
    assert clock.is_playing() is False


def test_pygame_audio_engine_load_sound_and_play_one_shot(pygame_audio_engine, synthetic_wav_factory):
    audio_path = synthetic_wav_factory(bpm=120.0, duration_seconds=0.5)
    pygame_audio_engine.load_sound("test_sfx", audio_path)

    pygame_audio_engine.play_one_shot("test_sfx")  # nao deve levantar erro


def test_pygame_audio_engine_plays_a_synthetic_track_headless(pygame_audio_engine, synthetic_wav_factory):
    audio_path = synthetic_wav_factory(bpm=120.0, duration_seconds=1.0)
    pygame_audio_engine.load_track("song", audio_path)

    pygame_audio_engine.play_track("song", start_offset_seconds=0.0)
    clock = pygame_audio_engine.get_clock()
    assert clock.is_playing() is True

    pygame_audio_engine.stop_track("song")
    assert clock.is_playing() is False


def test_pygame_audio_clock_now_seconds_is_zero_when_stopped_even_if_get_pos_is_dirty(
    pygame_audio_engine, synthetic_wav_factory
):
    """
    Regressao: o driver "dummy" do SDL (usado em testes headless) pode deixar
    `pygame.mixer.music.get_pos()` com um valor positivo/crescente "sujo" depois de
    `stop()`, mesmo com `get_busy()` corretamente voltando a `False` -- confirmado
    empiricamente rodando este mesmo cenario isoladamente. `now_seconds()` deve
    ignorar `get_pos()` quando `is_playing()` e falso, nunca reportar um tempo de
    reproducao falso para um clock que nao esta tocando.
    """
    audio_path = synthetic_wav_factory(bpm=120.0, duration_seconds=1.0)
    pygame_audio_engine.load_track("song", audio_path)
    clock = pygame_audio_engine.get_clock()

    pygame_audio_engine.play_track("song")
    time.sleep(0.2)  # deixa get_pos() acumular um valor real e positivo antes de parar
    pygame_audio_engine.stop_track("song")

    assert clock.is_playing() is False
    assert clock.now_seconds() == 0.0


def test_pygame_audio_clock_reflects_start_offset(pygame_audio_engine, synthetic_wav_factory):
    audio_path = synthetic_wav_factory(bpm=120.0, duration_seconds=2.0)
    pygame_audio_engine.load_track("song", audio_path)
    pygame_audio_engine.play_track("song", start_offset_seconds=0.5)

    clock = pygame_audio_engine.get_clock()
    # now_seconds() must be at least the start offset immediately after play()
    assert clock.now_seconds() >= 0.5
