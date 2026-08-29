"""Testes de MenuScene (ROADMAP M11.1) isolados de qualquer World/GameLoop real."""
from __future__ import annotations

from pathlib import Path

import pytest

from ouroboros.interfaces.null.null_input_provider import NullInputProvider
from ouroboros.interfaces.null.null_renderer import NullRenderer
from ouroboros.rhythm.loaders.song_catalog_loader import SongEntry

from games.rhythm_game.menu_scene import MenuScene

_SONG_A = SongEntry(track_id="song_a", display_name="Song A", beatmap_path=Path("a.json"), audio_path=Path("a.wav"))
_SONG_B = SongEntry(track_id="song_b", display_name="Song B", beatmap_path=Path("b.json"), audio_path=Path("b.wav"))
_ROWS = ((_SONG_A, "easy"), (_SONG_B, "hard"))


class _FakeGameLoop:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _press(input_provider: NullInputProvider, action_name: str) -> None:
    """Simula uma pressao de borda (`is_action_pressed` True neste frame,
    ate o proximo `poll()`) -- NAO libera sozinho, ao contrario de um
    "tap" completo: um segundo `poll()` sem `_release` antes reapresenta
    o mesmo estado `held=True` e a borda desaparece (`is_action_pressed`
    exige current=True E previous=False)."""
    input_provider.set_action_held(action_name, True)
    input_provider.poll()


def _release(input_provider: NullInputProvider, action_name: str) -> None:
    input_provider.set_action_held(action_name, False)
    input_provider.poll()


def test_construction_rejects_an_empty_row_list() -> None:
    with pytest.raises(ValueError):
        MenuScene(
            input_provider=NullInputProvider(),
            game_loop=_FakeGameLoop(),
            rows=(),
            on_confirm=lambda song, difficulty_id: None,
            viewport_size=(800, 600),
        )


def test_confirm_selection_calls_on_confirm_with_the_row_under_the_cursor() -> None:
    calls = []
    scene = MenuScene(
        input_provider=NullInputProvider(),
        game_loop=_FakeGameLoop(),
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: calls.append((song, difficulty_id)),
        viewport_size=(800, 600),
    )

    scene.confirm_selection()

    assert calls == [(_SONG_A, "easy")]


def test_move_down_advances_the_cursor_and_confirm_reflects_it() -> None:
    calls = []
    input_provider = NullInputProvider()
    scene = MenuScene(
        input_provider=input_provider,
        game_loop=_FakeGameLoop(),
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: calls.append((song, difficulty_id)),
        viewport_size=(800, 600),
    )

    _press(input_provider, "move_down")
    scene.update(world=None, delta_time=0.016)
    scene.confirm_selection()

    assert calls == [(_SONG_B, "hard")]


def test_cursor_wraps_around_past_the_last_row() -> None:
    calls = []
    input_provider = NullInputProvider()
    scene = MenuScene(
        input_provider=input_provider,
        game_loop=_FakeGameLoop(),
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: calls.append((song, difficulty_id)),
        viewport_size=(800, 600),
    )

    _press(input_provider, "move_down")
    scene.update(world=None, delta_time=0.016)
    _release(input_provider, "move_down")
    _press(input_provider, "move_down")
    scene.update(world=None, delta_time=0.016)  # de volta pra linha 0
    scene.confirm_selection()

    assert calls == [(_SONG_A, "easy")]


def test_cursor_wraps_around_before_the_first_row_via_move_up() -> None:
    calls = []
    input_provider = NullInputProvider()
    scene = MenuScene(
        input_provider=input_provider,
        game_loop=_FakeGameLoop(),
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: calls.append((song, difficulty_id)),
        viewport_size=(800, 600),
    )

    _press(input_provider, "move_up")  # linha 0 -1 -> ultima linha
    scene.update(world=None, delta_time=0.016)
    scene.confirm_selection()

    assert calls == [(_SONG_B, "hard")]


def test_quit_action_stops_the_game_loop() -> None:
    input_provider = NullInputProvider()
    game_loop = _FakeGameLoop()
    scene = MenuScene(
        input_provider=input_provider,
        game_loop=game_loop,
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: None,
        viewport_size=(800, 600),
    )

    _press(input_provider, "quit")
    scene.update(world=None, delta_time=0.016)

    assert game_loop.stopped is True


def test_render_does_not_crash_against_a_null_renderer() -> None:
    scene = MenuScene(
        input_provider=NullInputProvider(),
        game_loop=_FakeGameLoop(),
        rows=_ROWS,
        on_confirm=lambda song, difficulty_id: None,
        viewport_size=(800, 600),
    )

    scene.render(world=None, renderer=NullRenderer())
