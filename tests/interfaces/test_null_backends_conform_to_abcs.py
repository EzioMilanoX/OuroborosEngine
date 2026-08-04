# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import numpy as np

from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer


def test_null_renderer_is_a_real_irenderer(null_renderer):
    assert isinstance(null_renderer, IRenderer)
    null_renderer.begin_frame()
    empty = np.zeros((0, 2), dtype=np.float32)
    empty1d = np.zeros(0, dtype=np.float32)
    empty_int = np.zeros(0, dtype=np.int64)
    empty_rgba = np.zeros((0, 4), dtype=np.uint8)
    null_renderer.draw_batch(empty, empty1d, empty, empty_int, empty_rgba, empty_int, 0)
    null_renderer.end_frame()
    assert null_renderer.get_viewport_size() == (640, 480)
    null_renderer.shutdown()


def test_null_input_provider_is_a_real_iinputprovider(null_input_provider):
    assert isinstance(null_input_provider, IInputProvider)
    assert null_input_provider.is_action_held("fire") is False
    assert null_input_provider.get_axis("move_x") == 0.0
    assert null_input_provider.wants_quit() is False

    null_input_provider.set_action_held("fire", True)
    null_input_provider.poll()
    assert null_input_provider.is_action_pressed("fire") is True
    assert null_input_provider.is_action_held("fire") is True

    null_input_provider.poll()  # same held state, second frame -- no longer an edge
    assert null_input_provider.is_action_pressed("fire") is False
    assert null_input_provider.is_action_held("fire") is True

    null_input_provider.set_action_held("fire", False)
    null_input_provider.poll()
    assert null_input_provider.is_action_released("fire") is True
    assert null_input_provider.is_action_held("fire") is False


def test_null_input_provider_records_rumble_without_hardware(null_input_provider):
    assert null_input_provider._last_rumble is None
    null_input_provider.set_rumble(0.5, 1.0, 0.2)
    assert null_input_provider._last_rumble == (0.5, 1.0, 0.2)


def test_null_audio_engine_is_a_real_iaudioengine(null_audio_engine):
    assert isinstance(null_audio_engine, IAudioEngine)
    clock = null_audio_engine.get_clock()
    assert isinstance(clock, IAudioClock)

    null_audio_engine.load_track("song", "song.ogg")
    null_audio_engine.play_track("song", start_offset_seconds=1.5)
    assert clock.is_playing() is True
    assert clock.now_seconds() == 1.5

    null_audio_engine.stop_track("song")
    assert clock.is_playing() is False


def test_null_audio_clock_is_shared_between_engine_and_fixture(null_audio_engine, null_audio_clock):
    assert null_audio_clock is null_audio_engine.get_clock()


def test_null_audio_clock_advance_and_calibrate(null_audio_clock):
    assert null_audio_clock.now_seconds() == 0.0
    null_audio_clock.advance(2.0)
    assert null_audio_clock.now_seconds() == 2.0
    null_audio_clock.calibrate_latency(0.05)
    assert null_audio_clock.get_output_latency_seconds() == 0.05
